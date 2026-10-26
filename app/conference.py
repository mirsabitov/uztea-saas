import re
from decimal import Decimal

from django import forms
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .models import ConferenceRegistration
from click.models import Order
from payme.views import generate_payme_url

CONFERENCE_PRICE = Decimal('625000.00')


class ConferenceRegistrationForm(forms.ModelForm):
    accepted_terms = forms.BooleanField(
        required=True,
        error_messages={'required': 'Please accept the non-refundable registration fee terms to continue.'},
    )

    class Meta:
        model = ConferenceRegistration
        fields = ('full_name', 'email', 'job_title', 'organization', 'country', 'mobile_phone', 'accepted_terms')
        labels = {
            'full_name': 'Full name', 'email': 'Email address', 'job_title': 'Job title',
            'organization': 'University or company name', 'country': 'Country',
            'mobile_phone': 'Mobile phone',
        }
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Enter your full name', 'autocomplete': 'name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autocomplete': 'email'}),
            'job_title': forms.TextInput(attrs={'placeholder': 'e.g. English teacher', 'autocomplete': 'organization-title'}),
            'organization': forms.TextInput(attrs={'placeholder': 'Enter your university or company name', 'autocomplete': 'organization'}),
            'country': forms.TextInput(attrs={'placeholder': 'e.g. Uzbekistan', 'autocomplete': 'country-name'}),
            'mobile_phone': forms.TextInput(attrs={'type': 'tel', 'placeholder': '+998 90 123 45 67', 'autocomplete': 'tel', 'aria-describedby': 'phone-help'}),
        }

    def clean_mobile_phone(self):
        value = self.cleaned_data['mobile_phone']
        if not re.fullmatch(r'\+?[0-9 ()\-]+', value) or not 7 <= len(re.sub(r'\D', '', value)) <= 15:
            raise forms.ValidationError('Enter a valid phone number with 7–15 digits, including your country code.')
        return value


@csrf_protect
@require_http_methods(['GET', 'POST'])
def conference_register(request):
    form = ConferenceRegistrationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            registration = form.save()
            Order.objects.create(conference_registration=registration, amount=CONFERENCE_PRICE)
        request.session['tesol_payment_token'] = str(registration.payment_token)
        return redirect('conference_payment', token=registration.payment_token)
    return render(request, 'conference_form.html', {'form': form, 'price': CONFERENCE_PRICE})


@require_http_methods(['GET'])
def conference_success(request):
    token = request.session.get('tesol_payment_token')
    if not token:
        return redirect('conference_register')
    return redirect('conference_payment', token=token)


@never_cache
@require_http_methods(['GET'])
def conference_payment(request, token):
    order = get_object_or_404(Order.objects.select_related('conference_registration'),
                              conference_registration__payment_token=token)
    ready = bool(settings.PAYME_CASHBOX_ID and settings.PAYME_URL)
    return render(request, 'conference_form.html', {
        'submitted': True, 'order': order, 'price': order.amount,
        'payme_url': generate_payme_url(order) if ready and order.status != 'paid' else None,
    })
