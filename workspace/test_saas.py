from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from workspace.i18n import UZ, RU, translate
from workspace.models import Benefit, Event, OrganizationSettings


class LanguageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(self.admin)

    def test_switch_language_and_fallback(self):
        self.client.post(reverse('set_language'), {'language': 'uz', 'next': '/workspace/'})
        self.assertContains(self.client.get(reverse('workspace:home')), 'Odamlar')
        self.client.post(reverse('set_language'), {'language': 'ru', 'next': '/workspace/'})
        self.assertContains(self.client.get(reverse('workspace:home')), 'Люди')
        self.assertEqual(translate('uz', 'Text nobody translated'), 'Text nobody translated')

    def test_unknown_language_and_unsafe_next_are_ignored(self):
        response = self.client.post(reverse('set_language'), {'language': 'xx', 'next': 'https://evil.example/'})
        self.assertEqual(response['Location'], '/')
        self.assertContains(self.client.get(reverse('workspace:home')), 'People')

    def test_org_default_language(self):
        OrganizationSettings.objects.create(default_language='uz')
        self.assertContains(self.client.get(reverse('workspace:home')), 'Odamlar')

    def test_catalogues_have_the_same_keys(self):
        self.assertEqual(set(UZ), set(RU))


class SaasSettingsTests(TestCase):
    def test_edit_requires_permission(self):
        admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(admin)
        response = self.client.post(reverse('workspace:saas'), {
            'name': 'UzTEA', 'short_name': 'UzTEA', 'email': 'info@uztea.uz', 'website': 'https://www.uztea.uz',
            'default_language': 'ru'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OrganizationSettings.get().default_language, 'ru')

        viewer = User.objects.create_user('v', password='pw', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_organizationsettings'))
        self.client.force_login(viewer)
        self.client.post(reverse('workspace:saas'), {'name': 'X', 'short_name': 'X', 'default_language': 'en'})
        self.assertEqual(OrganizationSettings.get().default_language, 'ru')

        plain = User.objects.create_user('p', password='pw', is_staff=True)
        self.client.force_login(plain)
        self.assertEqual(self.client.get(reverse('workspace:saas')).status_code, 403)

    @override_settings(BREVO_SMTP_LOGIN='login', BREVO_SMTP_KEY='secret-brevo-key')
    def test_brevo_status_shown_without_the_key(self):
        admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(admin)
        response = self.client.get(reverse('workspace:saas'))
        self.assertContains(response, 'Brevo')
        self.assertNotContains(response, 'secret-brevo-key')


class EventsBenefitsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(self.admin)

    def test_create_event_and_benefit(self):
        start = (timezone.localtime() + timezone.timedelta(days=3)).strftime('%Y-%m-%dT%H:%M')
        self.client.post(reverse('workspace:event_add'), {'title': 'Workshop', 'kind': 'workshop', 'starts_at': start,
                                                           'is_published': 'on'})
        self.assertTrue(Event.objects.filter(title='Workshop', is_published=True).exists())
        self.assertContains(self.client.get(reverse('workspace:events')), 'Workshop')
        self.client.post(reverse('workspace:benefit_add'), {'title': 'Discount', 'is_active': 'on',
                                                             'membership_type_list': []})
        self.assertEqual(Benefit.objects.get().membership_types, '')

    def test_end_before_start_rejected(self):
        response = self.client.post(reverse('workspace:event_add'), {
            'title': 'Bad', 'kind': 'workshop', 'starts_at': '2026-11-10T10:00', 'ends_at': '2026-11-09T10:00'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())
