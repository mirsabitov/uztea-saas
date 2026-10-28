import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import Membership
from cabinet.accounts import get_or_create_member_user
from cabinet.models import MemberProfile, ProfileChange
from workspace.models import OrganizationSettings
from workspace.tests import make_membership

MEDIA = tempfile.mkdtemp()


def png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), '#1f6feb').save(buf, 'PNG')
    return buf.getvalue()


def profile_post(member, **changes):
    data = {
        'save_profile': '1', 'full_name': member.full_name, 'gender': member.gender or '', 'date_of_birth': '',
        'nationality': member.nationality, 'phone_number': member.phone_number, 'country': member.country,
        'region_city': member.region_city, 'address': '', 'position': member.position,
        'institution_name': member.institution_name, 'institution_type': member.institution_type,
        'experience': member.experience, 'subjects': '', 'levels': '', 'interests': '', 'join_sig': '',
        'sig_areas': '', 'contribution': '', 'participated_before': '', 'participation_details': '',
    }
    if member.agree_communication:
        data['agree_communication'] = 'on'
    data.update(changes)
    return data


@override_settings(MEDIA_ROOT=MEDIA)
class MyProfileTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.member = make_membership(full_name='Aziza Karimova', email='aziza@example.org', agree_communication=True)
        self.user = get_or_create_member_user(self.member.email)
        self.client.force_login(self.user)

    def test_profile_shows_every_application_question(self):
        response = self.client.get(reverse('cabinet:profile'))
        for label in ('Region / City', 'Areas of Professional Interest', 'How would you like to contribute to UzTEA?',
                      'Have you previously participated in UzTEA activities?', 'Membership type',
                      'I have read and agree to the UzTEA Membership Terms &amp; Conditions'):
            self.assertContains(response, label)
        self.assertContains(response, 'aziza@example.org')  # read-only

    def test_edit_saves_and_logs_changes(self):
        response = self.client.post(reverse('cabinet:profile'), profile_post(
            self.member, region_city='Samarkand', join_sig='True', sig_areas='Assessment'))
        self.assertRedirects(response, reverse('cabinet:profile'))
        self.member.refresh_from_db()
        self.assertEqual((self.member.region_city, self.member.join_sig, self.member.sig_areas),
                         ('Samarkand', True, 'Assessment'))
        change = ProfileChange.objects.get()
        self.assertEqual(change.changes['Region / City'], ['Tashkent', 'Samarkand'])

    def test_locked_fields_cannot_be_changed(self):
        self.client.post(reverse('cabinet:profile'), profile_post(
            self.member, email='hacker@example.org', membership_type='institutional', agree_terms='', consent_data='',
            is_pending_payment='on', payment_method='payme'))
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, 'aziza@example.org')
        self.assertEqual(self.member.membership_type, 'teacher')
        self.assertEqual(self.member.payment_method, 'atmos')

    def test_required_fields_are_checked(self):
        response = self.client.post(reverse('cabinet:profile'), profile_post(self.member, full_name=''))
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.full_name, 'Aziza Karimova')

    def test_photo_upload_and_remove(self):
        self.client.post(reverse('cabinet:profile'), {'save_photo': '1',
                                                      'photo': SimpleUploadedFile('me.png', png_bytes(), 'image/png')})
        profile = MemberProfile.objects.get(user=self.user)
        self.assertTrue(profile.photo)
        self.assertContains(self.client.get(reverse('cabinet:home')), profile.photo.url)
        self.client.post(reverse('cabinet:profile'), {'remove_photo': '1'})
        profile.refresh_from_db()
        self.assertFalse(profile.photo)
        bad = self.client.post(reverse('cabinet:profile'), {'save_photo': '1',
                                                            'photo': SimpleUploadedFile('x.png', b'not an image', 'image/png')})
        self.assertEqual(bad.status_code, 200)

    def test_subscription_switch(self):
        self.client.post(reverse('cabinet:subscription'), {})
        self.member.refresh_from_db()
        self.assertFalse(self.member.agree_communication)
        self.client.post(reverse('cabinet:subscription'), {'subscribed': 'on'})
        self.member.refresh_from_db()
        self.assertTrue(self.member.agree_communication)
        self.assertEqual(ProfileChange.objects.count(), 2)

    def test_staff_sees_unsubscribed_and_member_edits(self):
        self.client.post(reverse('cabinet:subscription'), {})
        admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(admin)
        people = self.client.get(reverse('workspace:people'), {'subscribed': 'no'})
        self.assertEqual([r['pk'] for r in people.context['rows']], [self.member.pk])
        profile = self.client.get(reverse('workspace:member_profile', args=[self.member.pk]))
        self.assertContains(profile, 'Profile updated by the member')
        admin_list = self.client.get(reverse('admin:app_membership_changelist'), {'agree_communication__exact': '0'})
        self.assertContains(admin_list, 'Aziza Karimova')


@override_settings(MEDIA_ROOT=MEDIA)
class BrandingTests(TestCase):
    def test_upload_and_remove_logo(self):
        admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(admin)
        base = {'name': 'UzTEA', 'short_name': 'UzTEA', 'email': 'info@uztea.uz', 'website': 'https://www.uztea.uz',
                'default_language': 'en'}
        self.client.post(reverse('workspace:saas'), dict(base, logo_dark=SimpleUploadedFile('w.png', png_bytes(), 'image/png')))
        org = OrganizationSettings.get()
        self.assertTrue(org.logo_dark)
        self.assertContains(self.client.get(reverse('workspace:home')), org.logo_dark.url)
        self.client.post(reverse('workspace:saas'), dict(base, clear_logo_dark='on'))
        org.refresh_from_db()
        self.assertFalse(org.logo_dark)
        self.assertIn('logo-white', org.logo_urls()['dark'])
        too_big = SimpleUploadedFile('t.txt', b'x', 'text/plain')
        response = self.client.post(reverse('workspace:saas'), dict(base, logo_light=too_big))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(OrganizationSettings.get().logo_light)
