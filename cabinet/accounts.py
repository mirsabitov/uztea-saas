"""Member accounts: one Django user per email, linked to memberships by that email.

Members never get staff rights, so they cannot open the workspace or the admin.
Account creation, admin invitations and password resets all use the same thing: an
emailed link (Django's password-reset token) to set a password.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)
User = get_user_model()


def cabinet_base():
    import os
    return os.getenv('CABINET_BASE_URL', getattr(settings, 'SITE_BASE_URL', 'https://uztea.uz')).rstrip('/')


def memberships_for_email(email):
    from app.models import Membership
    if not email:
        return Membership.objects.none()
    return Membership.objects.filter(email__iexact=email.strip()).order_by('-created_at')


def get_or_create_member_user(email, full_name=''):
    """The member's user (created without a usable password). Staff accounts are left alone."""
    email = email.strip().lower()
    user = User.objects.filter(email__iexact=email).order_by('pk').first() or User.objects.filter(username__iexact=email).first()
    if user:
        return user
    first, _, last = (full_name or '').strip().partition(' ')
    user = User(username=email, email=email, first_name=first[:150], last_name=last[:150])
    user.set_unusable_password()
    user.save()
    return user


def password_link(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return cabinet_base() + reverse('cabinet:set_password', args=[uid, token])


def send_password_link(email, *, invited_by=None, lang='en'):
    """Email a set-password link if this email belongs to a membership. Returns True when sent."""
    memberships = memberships_for_email(email)
    member = memberships.first()
    if member is None:
        return False
    user = get_or_create_member_user(member.email, member.full_name)
    if user.is_staff:
        return False  # staff use the workspace login, not the cabinet
    link = password_link(user)
    html = render_to_string('cabinet/email_password.html', {
        'name': member.full_name, 'link': link, 'invited': bool(invited_by),
        'has_password': user.has_usable_password(), 'lang': lang,
    })
    subject = 'Your UzTEA profile is ready' if invited_by else 'Set your UzTEA profile password'
    message = EmailMultiAlternatives(subject=subject, body=strip_tags(html).strip() + f'\n\n{link}',
                                     from_email=settings.DEFAULT_FROM_EMAIL,
                                     to=[member.email])
    message.attach_alternative(html, 'text/html')
    message.send(fail_silently=False)
    if invited_by is not None:
        import uuid
        from workspace.models import MessageLog
        MessageLog.objects.create(batch=uuid.uuid4(), channel='email', source='cabinet', recipient_id=member.pk,
                                  recipient_name=member.full_name[:255], to=member.email, subject=subject,
                                  body='Cabinet invitation (set-password link)', status='sent', sent_by=invited_by)
    return True
