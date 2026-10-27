"""My profile: the membership application's questions, editable by the member.

Labels and widgets come from the public application form (app.forms.MembershipForm),
so the profile asks exactly the same questions. Payment data, membership type and ID,
email (the login) and the legal consents cannot be changed here.
"""
from django import forms

from app.forms import MembershipForm
from app.models import Membership

from .models import ProfileChange

# Same steps as /apply/
STEPS = [
    ('Personal information', ['full_name', 'gender', 'date_of_birth', 'nationality', 'phone_number', 'email',
                              'country', 'region_city', 'address']),
    ('Professional details', ['position', 'institution_name', 'institution_type', 'experience', 'subjects', 'levels']),
    ('Interests & engagement', ['membership_type', 'interests', 'join_sig', 'sig_areas', 'contribution',
                                'participated_before', 'participation_details']),
    ('Institution members', ['member_2_name', 'member_2_email', 'member_3_name', 'member_3_email',
                             'member_4_name', 'member_4_email', 'member_5_name', 'member_5_email']),
    ('Preferences & consents', ['agree_terms', 'consent_data', 'agree_communication']),
]
READ_ONLY = {'email', 'membership_type', 'agree_terms', 'consent_data'}
INSTITUTION_FIELDS = set(STEPS[3][1])
EDITABLE = [f for _title, names in STEPS for f in names if f not in READ_ONLY]
YES_NO = [('True', 'Yes'), ('False', 'No')]  # these fields are yes/no in the database
SUBSCRIBE_LABEL = 'Send me UzTEA news, events and announcements by email'


def _bool_or_none(value):
    return {'True': True, 'False': False}.get(value)


class ProfileForm(forms.ModelForm):
    join_sig = forms.TypedChoiceField(choices=YES_NO, coerce=_bool_or_none, required=False, empty_value=False)
    participated_before = forms.TypedChoiceField(choices=YES_NO, coerce=_bool_or_none, required=False, empty_value=False)

    class Meta:
        model = Membership
        fields = EDITABLE
        labels = dict(MembershipForm.Meta.labels, agree_communication=SUBSCRIBE_LABEL)
        widgets = {k: v for k, v in MembershipForm.Meta.widgets.items() if k in EDITABLE
                   and k not in ('join_sig', 'participated_before')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.membership_type != 'institutional':
            for name in INSTITUTION_FIELDS:
                self.fields.pop(name, None)
        self.fields['join_sig'].label = MembershipForm.Meta.labels['join_sig']
        self.fields['participated_before'].label = MembershipForm.Meta.labels['participated_before']
        for name in ('join_sig', 'participated_before'):
            value = getattr(self.instance, name)
            self.initial[name] = str(bool(value))
        for field in self.fields.values():
            if hasattr(field, 'choices') and not isinstance(field, forms.TypedChoiceField):
                choices = list(field.choices)
                if choices and choices[0][0] in ('', None):
                    choices[0] = ('', 'Select an option')
                    field.choices = choices

    def save_with_log(self, user):
        """Save and remember what changed (shown to staff in the member's activity)."""
        before = Membership.objects.get(pk=self.instance.pk)
        obj = self.save()
        changes = {}
        for name in self.changed_data:
            old, new = display(before, name), display(obj, name)
            if old != new:
                changes[str(self.fields[name].label or name)[:80]] = [old, new]
        if changes:
            ProfileChange.objects.create(membership=obj, user=user, changes=changes)
        return changes


def display(membership, name):
    value = getattr(membership, name)
    field = Membership._meta.get_field(name)
    if name == 'membership_type':
        return membership.get_membership_type_display()
    if field.choices:
        return getattr(membership, f'get_{name}_display')() or ''
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%d.%m.%Y')
    return str(value)


def read_only_rows(membership):
    labels = dict(MembershipForm.Meta.labels)
    names = {'email': 'Email', 'membership_type': 'Membership type'}
    return {name: {'label': labels.get(name) or names.get(name) or Membership._meta.get_field(name).verbose_name.capitalize(),
                   'value': display(membership, name)} for name in READ_ONLY}


class PhotoForm(forms.Form):
    photo = forms.ImageField(required=False)

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and photo.size > 3 * 1024 * 1024:
            raise forms.ValidationError('Use a photo up to 3 MB.')
        return photo
