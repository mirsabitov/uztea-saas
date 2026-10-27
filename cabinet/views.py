"""UzTEA member cabinet (/account/): sign in, set a password from an emailed link, see your membership."""
import logging

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from workspace.i18n import LANGUAGES, language_for, set_language, translate

from .accounts import memberships_for_email, send_password_link

logger = logging.getLogger(__name__)
User = get_user_model()
ATTEMPTS_PER_HOUR = 10


def _ctx(request, **extra):
    from workspace.models import OrganizationSettings
    return {'lang': language_for(request), 'languages': LANGUAGES, 'org': OrganizationSettings.get(), **extra}


def _limited(request, bucket):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')
    key = f'cabinet-{bucket}:{ip}'
    try:
        count = cache.get(key, 0)
        if count >= ATTEMPTS_PER_HOUR:
            return True
        cache.set(key, count + 1, 3600)
    except Exception:
        pass
    return False


def _member_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('cabinet:login') + f'?next={request.path}')
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


@csrf_protect
def login_view(request):
    lang = language_for(request)
    if request.user.is_authenticated and not request.user.is_staff:
        return redirect('cabinet:home')
    form = LoginForm(request.POST or None)
    error = ''
    if request.method == 'POST':
        if _limited(request, 'login'):
            error = translate(lang, 'Too many requests. Please try again in an hour.')
        elif form.is_valid():
            email = form.cleaned_data['email'].strip().lower()
            account = User.objects.filter(email__iexact=email).order_by('pk').first()
            user = authenticate(request, username=account.username if account else email,
                                password=form.cleaned_data['password'])
            if user is not None and user.is_active:
                login(request, user)
                set_language(request, lang)  # login starts a fresh session
                target = request.GET.get('next', '')
                return redirect(target if target.startswith('/account/') else reverse('cabinet:home'))
            error = translate(lang, 'Incorrect email or password.')
    return render(request, 'cabinet/login.html', _ctx(request, form=form, error=error))


@require_POST
def logout_view(request):
    logout(request)
    return redirect('cabinet:login')


@csrf_protect
def request_link(request):
    """Create an account or reset a password: we email a link if the email belongs to a membership."""
    sent = False
    error = ''
    lang = language_for(request)
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()
        if _limited(request, 'link'):
            error = translate(lang, 'Too many requests. Please try again in an hour.')
        elif not email or '@' not in email:
            error = translate(lang, 'Enter the email you used on the membership form.')
        else:
            try:
                send_password_link(email, lang=lang)
            except Exception as exc:
                logger.warning('Cabinet link email failed: %s', exc)
            sent = True  # same answer whether or not the email is known
    return render(request, 'cabinet/request_link.html', _ctx(request, sent=sent, error=error,
                                                             mode=request.GET.get('mode', 'register')))


class SetPasswordForm(forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if data.get('password1') != data.get('password2'):
            raise ValidationError('The two passwords do not match.')
        # The project's AUTH_PASSWORD_VALIDATORS are off, so the cabinet sets its own minimum.
        if len(data.get('password1') or '') < 8:
            raise ValidationError('Use at least 8 characters.')
        validate_password(data.get('password1') or '', self.user)
        return data


@csrf_protect
def set_password(request, uidb64, token):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    valid = user is not None and not user.is_staff and default_token_generator.check_token(user, token)
    form = SetPasswordForm(user, request.POST or None) if valid else None
    if valid and request.method == 'POST' and form.is_valid():
        user.set_password(form.cleaned_data['password1'])
        user.save()
        lang = language_for(request)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        set_language(request, lang)  # login starts a fresh session
        messages.success(request, translate(lang, 'Your password is set. Welcome!'))
        return redirect('cabinet:home')
    return render(request, 'cabinet/set_password.html', _ctx(request, form=form, valid=valid))


@_member_required
def home(request):
    from app import membership_lifecycle as lifecycle
    from app.models import AnniversaryRegistration, ConferenceRegistration
    from certificates.emails import download_url
    from certificates.models import Certificate
    from click.models import Order
    from workspace.models import Benefit, Event

    email = request.user.email or request.user.username
    memberships = list(memberships_for_email(email))
    statuses = lifecycle.bulk_status(memberships) if memberships else {}
    # Show the membership that matters most: valid first, then the newest.
    rank = {lifecycle.ACTIVE: 0, lifecycle.RENEWAL_DUE: 0, lifecycle.EXPIRED: 1, lifecycle.PENDING: 2, lifecycle.NO_RECORD: 3}
    memberships.sort(key=lambda m: (rank.get(statuses[m.pk]['key'], 9), -m.created_at.timestamp()))
    member = memberships[0] if memberships else None
    status = statuses.get(member.pk) if member else None
    is_active = bool(status and status['key'] in (lifecycle.ACTIVE, lifecycle.RENEWAL_DUE))

    orders = list(Order.objects.filter(membership__in=memberships).order_by('-created_at')) if memberships else []
    conference = list(ConferenceRegistration.objects.filter(email__iexact=email).select_related('order'))
    anniversary = list(AnniversaryRegistration.objects.filter(email__iexact=email))
    certs = Certificate.objects.filter(Q(email__iexact=email) | Q(membership__in=memberships),
                                       status=Certificate.ACTIVE).distinct().order_by('-created_at')
    today = timezone.localdate()
    benefits = []
    if member and is_active:
        benefits = [b for b in Benefit.objects.filter(is_active=True).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today))
                    .select_related('partner') if b.applies_to(member.membership_type)]
    events = Event.objects.filter(is_published=True, starts_at__gte=timezone.now())
    if not is_active:
        events = events.filter(members_only=False)
    return render(request, 'cabinet/home.html', _ctx(
        request, member=member, status=status, is_active=is_active, memberships=memberships,
        membership_id=f'UZ{member.pk:06d}' if member else '',
        card_url=reverse('membership_card', args=[member.pk]) + '?download=1' if member and is_active else None,
        orders=orders, conference=conference, anniversary=anniversary,
        certificates=[{'c': c, 'url': download_url(c)} for c in certs],
        benefits=benefits, events=list(events[:10]),
        renew_url=reverse('membership_form'),
    ))
