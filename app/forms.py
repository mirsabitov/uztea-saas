from django import forms
from .models import Membership, MembershipTypeConfig
from .pricing import format_membership_price


def get_active_membership_configs():
    try:
        return {c.membership_type: c for c in MembershipTypeConfig.objects.filter(is_active=True)}
    except Exception:
        return {}


class MembershipForm(forms.ModelForm):
    membership_type = forms.ChoiceField(label='Membership type')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_method'].required = False
        self.fields['payment_method'].initial = 'atmos'
        self.fields['payment_method'].widget = forms.HiddenInput()
        # Consent checkboxes must be checked
        for consent_field in ('agree_terms', 'consent_data', 'agree_communication'):
            self.fields[consent_field].required = True
        for field_name, field in self.fields.items():
            if hasattr(field, 'choices'):
                choices = list(field.choices)
                if choices and choices[0][0] in ('', None) and choices[0][1] == '---------':
                    choices[0] = (choices[0][0], 'Select an option')
                    field.choices = choices
        active_configs = get_active_membership_configs()
        # Membership types are managed from the admin panel.
        if active_configs:
            self.fields['membership_type'].choices = [
                ('', 'Select an option'),
                *((code, config.name) for code, config in active_configs.items()),
            ]
        else:
            self.fields['membership_type'].choices = [
                ('', 'Select an option'),
                *Membership.MEMBERSHIP_TYPE_CHOICES,
            ]
        self.membership_type_cards = self._membership_type_cards(active_configs)

    def _membership_type_cards(self, active_configs=None):
        badges = {
            'basic': 'Starter',
            'student': 'Discounted',
            'teacher': 'Popular',
            'institutional': 'Team',
        }
        seats = {
            'basic': 1,
            'student': 1,
            'teacher': 1,
            'institutional': 4,
        }
        cards = []
        type_choices = (
            [(code, config.name) for code, config in active_configs.items()]
            if active_configs else Membership.MEMBERSHIP_TYPE_CHOICES
        )
        for value, label in type_choices:
            # Use DB price if available
            if active_configs:
                price = f"{active_configs[value].price:,.0f} UZS"
            else:
                price = format_membership_price(value)
            seat_count = seats.get(value, 1)
            cards.append({
                'value': value,
                'label': label,
                'price': price,
                'badge': badges.get(value, 'Plan'),
                'seats': seat_count,
                'seats_text': f"{seat_count} member" if seat_count == 1 else f"{seat_count} members",
            })
        return cards

    def clean_payment_method(self):
        return 'atmos'

    def clean(self):
        cleaned = super().clean()
        # When Institutional, all 4 members (name + email) are required
        if cleaned.get('membership_type') == 'institutional':
            member_fields = []
            for n in (2, 3, 4, 5):
                member_fields.append((f'member_{n}_name', 'name'))
                member_fields.append((f'member_{n}_email', 'email'))
            for field_name, kind in member_fields:
                if not cleaned.get(field_name):
                    self.add_error(
                        field_name,
                        'This field is required for Institutional membership.'
                    )
        return cleaned

    class Meta:
        model = Membership
        exclude = ['motivation', 'challenges', 'expectations', 'preferred_language', 'contact_method',
                   'institution_teachers_count', 'contact_person_name', 'contact_person_email', 'collaboration_interest']

        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'e.g., John Doe'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'nationality': forms.TextInput(attrs={'placeholder': 'e.g., Uzbek, American'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '+998 90 123 45 67'}),
            'email': forms.EmailInput(attrs={'placeholder': 'john.doe@example.com'}),
            'country': forms.TextInput(attrs={'placeholder': 'e.g., Uzbekistan'}),
            'region_city': forms.TextInput(attrs={'placeholder': 'e.g., Tashkent / Yunusabad'}),
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Full residential or work address (Optional)'}),
            'institution_name': forms.TextInput(attrs={'placeholder': 'Name of your school, university, or organization'}),
            'subjects': forms.TextInput(attrs={'placeholder': 'e.g., General English, IELTS, ESP'}),
            'levels': forms.TextInput(attrs={'placeholder': 'e.g., Primary, Secondary, University, Adults'}),
            'interests': forms.Textarea(attrs={'rows': 2, 'placeholder': 'e.g., Teacher Training, AI in Education, Curriculum Design'}),
            'sig_areas': forms.Textarea(attrs={'rows': 2, 'placeholder': 'If you selected Yes above, please list the SIG areas here...'}),
            'contribution': forms.Textarea(attrs={'rows': 2, 'placeholder': 'e.g., Attend events, presentation, volunteering...'}),
            'participation_details': forms.Textarea(attrs={'rows': 2, 'placeholder': 'If you selected Yes above, in which activities did you participate?'}),
            'institution_teachers_count': forms.NumberInput(attrs={'placeholder': 'e.g., 5'}),
            'contact_person_name': forms.TextInput(attrs={'placeholder': 'Name of the main contact person'}),
            'contact_person_email': forms.EmailInput(attrs={'placeholder': 'contact@institution.com'}),
            'collaboration_interest': forms.Textarea(attrs={'rows': 2, 'placeholder': 'How would your institution like to collaborate with UzTEA?'}),
            'member_2_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'member_2_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'member_3_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'member_3_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'member_4_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'member_4_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'member_5_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'member_5_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'motivation': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Briefly describe your motivation...'}),
            'challenges': forms.Textarea(attrs={'rows': 2, 'placeholder': 'What challenges do you face in your teaching context?'}),
            'expectations': forms.Textarea(attrs={'rows': 2, 'placeholder': 'What resources or support do you expect?'}),
            'join_sig': forms.Select(choices=[(None, 'Select an option'), (True, 'Yes'), (False, 'No')]),
            'participated_before': forms.Select(choices=[(None, 'Select an option'), (True, 'Yes'), (False, 'No')]),
            'agree_terms': forms.CheckboxInput(),
            'consent_data': forms.CheckboxInput(),
            'agree_communication': forms.CheckboxInput(),
            'payment_proof': forms.FileInput(attrs={'class': 'file-input-custom'}),
        }

        labels = {
            'region_city': 'Region / City',
            'join_sig': 'Would you like to join a SIG (Special Interest Group)?',
            'sig_areas': 'SIG Areas of Interest',
            'interests': 'Areas of Professional Interest',
            'contribution': 'How would you like to contribute to UzTEA?',
            'participated_before': 'Have you previously participated in UzTEA activities?',
            'participation_details': 'Participation Details',
            'institution_teachers_count': 'Number of teachers applying',
            'collaboration_interest': 'Areas of collaboration interest',
            'motivation': 'Why do you want to join UzTEA?',
            'challenges': 'What challenges do you face as an English teacher?',
            'expectations': 'What kind of support do you expect from UzTEA?',
            'agree_terms': 'I have read and agree to the UzTEA Membership Terms & Conditions',
            'consent_data': 'I consent to the processing of my personal data in accordance with applicable data protection laws and the Privacy Policy',
            'agree_communication': 'I agree to receive updates, announcements, and communications from UzTEA',
        }

        help_texts = {
            'interests': None,
            'contribution': None,
        }
