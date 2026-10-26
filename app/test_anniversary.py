from django.contrib.auth.models import Permission, User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import AnniversaryRegistration


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AnniversaryAdminEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('event_admin', is_staff=True)
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label='app', codename='change_anniversaryregistration',
        ))
        self.client.force_login(self.user)
        self.selected = AnniversaryRegistration.objects.create(
            full_name='Selected attendee', email='selected@example.com',
            phone_number='+998901234567', membership_status='yes', event_communication=True,
        )
        self.other = AnniversaryRegistration.objects.create(
            full_name='Other attendee', email='other@example.com',
            phone_number='+998901234568', membership_status='not_yet', event_communication=True,
        )
        self.list_url = reverse('admin:app_anniversaryregistration_changelist')
        self.compose_url = reverse('admin:app_membership_compose_email')

    def select_recipient(self):
        return self.client.post(self.list_url, {
            'action': 'compose_custom_email', '_selected_action': [self.selected.pk],
        })

    def test_selection_opens_existing_composer_for_anniversary_only(self):
        response = self.select_recipient()
        self.assertRedirects(response, self.compose_url)
        response = self.client.get(self.compose_url)
        self.assertEqual(response.context['recipient_count'], 1)
        self.assertEqual(list(response.context['recipients']), [self.selected])
        self.assertEqual(response.context['changelist_url'], self.list_url)
        self.assertEqual(response.context['opts'].model, AnniversaryRegistration)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_uses_selected_email_and_returns_to_registrations(self):
        self.select_recipient()
        response = self.client.post(self.compose_url, {
            'sender': 'uztea', 'template': 'uztea_brand',
            'subject': 'Event reminder', 'body': '<p>See you at the celebration!</p>',
        })
        self.assertRedirects(response, self.list_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['selected@example.com'])
        self.assertEqual(mail.outbox[0].subject, 'Event reminder')
        self.assertIn('Selected attendee', mail.outbox[0].alternatives[0][0])
        self.assertNotIn('custom_email_model', self.client.session)

    def test_view_only_admin_cannot_use_action_or_send(self):
        self.select_recipient()
        self.user.user_permissions.clear()
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label='app', codename='view_anniversaryregistration',
        ))
        response = self.client.get(self.list_url)
        self.assertNotContains(response, 'Send custom email to selected registrations')
        self.assertEqual(self.client.get(self.compose_url).status_code, 403)
        response = self.client.post(self.compose_url, {
            'sender': 'uztea', 'template': 'custom', 'subject': 'Blocked', 'body': 'Blocked',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)


class AnniversaryRegistrationTests(TestCase):
    data = {
        'full_name': 'Test Teacher', 'phone_number': '+998 90 123 45 67',
        'email': 'teacher@example.com', 'membership_status': 'not_yet',
        'event_communication': 'on',
    }

    def test_page_contains_event_details_and_membership_link(self):
        response = self.client.get(reverse('anniversary_register'))
        self.assertContains(response, 'Panarams Hotel Tashkent')
        self.assertNotContains(response, 'Celebration program')
        self.assertContains(response, reverse('membership_form'))

    def test_registration_and_refresh_preserve_optional_consent_defaults(self):
        response = self.client.post(reverse('anniversary_register'), self.data)
        self.assertRedirects(response, reverse('anniversary_success'))
        registration = AnniversaryRegistration.objects.get()
        self.assertTrue(registration.event_communication)
        self.assertFalse(registration.future_updates)
        self.assertFalse(registration.photos_videos)
        response = self.client.get(reverse('anniversary_success'))
        self.assertContains(response, 'Thank you for registering!')
        self.assertEqual(AnniversaryRegistration.objects.count(), 1)

    def test_optional_consents_saved_when_selected(self):
        self.client.post(reverse('anniversary_register'), {
            **self.data, 'membership_status': 'yes', 'future_updates': 'on', 'photos_videos': 'on',
        })
        registration = AnniversaryRegistration.objects.get()
        self.assertTrue(registration.future_updates)
        self.assertTrue(registration.photos_videos)

    def test_invalid_fields_do_not_save_and_preserve_entered_name(self):
        for field, value in [('full_name', ' '), ('email', 'invalid'),
                             ('phone_number', 'abc'), ('membership_status', ''),
                             ('membership_status', 'invalid'), ('event_communication', '')]:
            with self.subTest(field=field, value=value):
                response = self.client.post(reverse('anniversary_register'), {**self.data, field: value})
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
                self.assertFalse(AnniversaryRegistration.objects.exists())
                if field != 'full_name':
                    self.assertContains(response, 'Test Teacher')

    def test_success_requires_registration_session(self):
        self.assertRedirects(self.client.get(reverse('anniversary_success')), reverse('anniversary_register'))

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('anniversary_register'), self.data).status_code, 403)
        client.get(reverse('anniversary_register'))
        response = client.post(reverse('anniversary_register'), {
            **self.data, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        })
        self.assertEqual(response.status_code, 302)
