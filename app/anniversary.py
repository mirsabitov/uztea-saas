import re

from django import forms
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .models import AnniversaryRegistration


PROGRAM = [
    ('09:30–10:00', 'Registration and welcome networking'),
    ('10:00–10:40', 'Welcome remarks and 30th anniversary celebration notes'),
    ('10:40–11:00', 'Coffee break and networking'),
    ('11:00–11:30', 'Parallel sessions: ETS/TOEFL guest speaker / Justin Erkess, Mapping Fluency: Teaching English Through a Geographic Lens'),
    ('11:30–12:00', 'Parallel sessions: UzTEA partner presentation / ETS/TOEFL guest speaker'),
    ('12:00–12:30', 'Closing, awards, and group photo'),
]


class AnniversaryRegistrationForm(forms.ModelForm):
    event_communication = forms.BooleanField(
        required=True,
        label='I agree that UzTEA may use my contact details to send me information about this event.',
    )
    membership_status = forms.ChoiceField(
        choices=AnniversaryRegistration._meta.get_field('membership_status').choices,
        widget=forms.RadioSelect,
        label='Are you currently a member of UzTEA?',
    )

    class Meta:
        model = AnniversaryRegistration
        fields = ('full_name', 'phone_number', 'email', 'membership_status',
                  'event_communication', 'future_updates', 'photos_videos')
        labels = {
            'email': 'Email address',
            'future_updates': 'I would like to receive updates about future UzTEA events, membership, and activities.',
            'photos_videos': 'I agree that photos or videos of me taken during this event may be used in UzTEA’s event coverage and promotional materials.',
        }
        widgets = {
            'full_name': forms.TextInput(attrs={'autocomplete': 'name', 'placeholder': 'Your full name'}),
            'phone_number': forms.TextInput(attrs={'type': 'tel', 'autocomplete': 'tel', 'placeholder': '+998 90 123 45 67'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email', 'placeholder': 'you@example.com'}),
        }

    def clean_phone_number(self):
        value = self.cleaned_data['phone_number']
        if not re.fullmatch(r'\+?[0-9 ()\-]+', value) or not 7 <= len(re.sub(r'\D', '', value)) <= 15:
            raise forms.ValidationError('Enter a valid phone number with 7–15 digits, including your country code.')
        return value


@never_cache
@csrf_protect
@require_http_methods(['GET', 'POST'])
def anniversary_register(request):
    form = AnniversaryRegistrationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        request.session['anniversary_registered'] = True
        return redirect('anniversary_success')
    return render(request, 'anniversary_form.html', {'form': form, 'program': PROGRAM})


@never_cache
@require_http_methods(['GET'])
def anniversary_success(request):
    if not request.session.get('anniversary_registered'):
        return redirect('anniversary_register')
    return render(request, 'anniversary_form.html', {'submitted': True, 'program': PROGRAM})
