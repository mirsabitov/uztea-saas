import base64
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import ConferenceRegistration, Membership
from click.models import Order
from payme.views import generate_payme_url


class ConferenceAdminVisibilityTests(TestCase):
    def test_all_registrations_are_visible_and_exportable(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from .admin import ConferenceRegistrationAdmin, ConferenceRegistrationResource

        model_admin = ConferenceRegistrationAdmin(ConferenceRegistration, AdminSite())
        request = RequestFactory().get('/admin/app/conferenceregistration/')
        for status in ('pending', 'processing', 'paid', 'failed'):
            registration = ConferenceRegistration.objects.create(
                full_name=status, email=f'{status}@example.com', job_title='Teacher',
                organization='University', country='Uzbekistan', mobile_phone='+998901234567',
            )
            Order.objects.create(conference_registration=registration, amount=625000, status=status)
        ConferenceRegistration.objects.create(full_name='No order')

        queryset = model_admin.get_queryset(request)
        self.assertEqual(queryset.count(), 5)
        exported = ConferenceRegistrationResource().export(queryset)
        self.assertEqual(exported.height, 5)
        self.assertIn('payment_status', exported.headers)
        self.assertEqual(
            {row['payment_status'] for row in exported.dict},
            {'Pending', 'Processing', 'Paid', 'Failed', 'No payment order'},
        )
        self.assertEqual(ConferenceRegistration.objects.count(), 5)

    def test_changelist_shows_import_and_export_links(self):
        user = get_user_model().objects.create_superuser(
            username='tesol-admin', email='admin@example.com', password='test-password'
        )
        self.client.force_login(user)
        response = self.client.get(reverse('admin:app_conferenceregistration_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('admin:app_conferenceregistration_import'))
        self.assertContains(response, reverse('admin:app_conferenceregistration_export'))

    def test_import_updates_existing_and_adds_new_without_changing_payment(self):
        from tablib import Dataset
        from .admin import ConferenceRegistrationResource

        paid = ConferenceRegistration.objects.create(full_name='Original')
        Order.objects.create(conference_registration=paid, amount=625000, status='paid')
        resource = ConferenceRegistrationResource()
        dataset = Dataset(headers=['id', 'full_name'])
        dataset.append((paid.pk, 'Updated'))
        result = resource.import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertFalse(result.has_validation_errors())
        paid.refresh_from_db()
        self.assertEqual(paid.full_name, 'Updated')

        dataset = Dataset(headers=[
            'id', 'full_name', 'email', 'job_title', 'organization',
            'country', 'mobile_phone', 'payment_status',
        ])
        dataset.append(('', 'Imported', 'imported@example.com', 'Teacher',
                        'University', 'Uzbekistan', '+998901234567', 'Paid'))
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        self.assertFalse(result.has_validation_errors())
        imported = ConferenceRegistration.objects.get(full_name='Imported')
        self.assertFalse(Order.objects.filter(conference_registration=imported).exists())
        self.assertEqual(ConferenceRegistration.objects.count(), 2)


class ConferenceRegistrationTests(TestCase):
    data = {
        'full_name': 'Jane Smith', 'email': 'jane@example.com',
        'job_title': 'Lecturer', 'organization': 'Example University',
        'country': 'Uzbekistan', 'mobile_phone': '+998 90 123 45 67',
        'accepted_terms': 'on',
    }

    def test_submit_saves_conference_registration_without_creating_membership(self):
        response = self.client.post(reverse('conference_register'), self.data)
        registration = ConferenceRegistration.objects.get()
        self.assertRedirects(response, reverse('conference_payment', args=[registration.payment_token]))
        self.assertEqual(registration.order.amount, Decimal('625000.00'))
        self.assertTrue(registration.accepted_terms)
        self.assertEqual(ConferenceRegistration.objects.get().organization, 'Example University')
        self.assertEqual(Membership.objects.count(), 0)
        self.client.get(reverse('conference_success'))
        self.assertEqual(ConferenceRegistration.objects.count(), 1)

    def test_all_six_fields_and_terms_are_required(self):
        response = self.client.post(reverse('conference_register'), {})
        self.assertEqual(len(response.context['form'].errors), 7)
        self.assertEqual(ConferenceRegistration.objects.count(), 0)

    def test_terms_must_be_explicitly_accepted_before_order_creation(self):
        data = {key: value for key, value in self.data.items() if key != 'accepted_terms'}
        response = self.client.post(reverse('conference_register'), data)
        self.assertIn('accepted_terms', response.context['form'].errors)
        self.assertEqual(ConferenceRegistration.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)

    def test_invalid_email_and_phone_are_rejected_and_values_preserved(self):
        response = self.client.post(reverse('conference_register'), {
            **self.data, 'email': 'invalid', 'mobile_phone': 'letters123',
        })
        self.assertIn('email', response.context['form'].errors)
        self.assertIn('mobile_phone', response.context['form'].errors)
        self.assertContains(response, 'Jane Smith')
        self.assertEqual(ConferenceRegistration.objects.count(), 0)

    def test_csrf_is_required_even_without_global_middleware(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('conference_register'), self.data).status_code, 403)
        client.get(reverse('conference_register'))
        response = client.post(reverse('conference_register'), {
            **self.data, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        })
        self.assertEqual(response.status_code, 302)

    def test_success_requires_submission(self):
        self.assertRedirects(self.client.get(reverse('conference_success')), reverse('conference_register'))


@override_settings(PAYME_CASHBOX_ID='test-merchant', PAYME_SECRET_KEY='test-secret',
                   PAYME_URL='https://checkout.test.paycom.uz', SITE_BASE_URL='https://example.com')
class ConferencePaymentTests(TestCase):
    def setUp(self):
        self.client.post(reverse('conference_register'), {
            **ConferenceRegistrationTests.data, 'amount': '1', 'status': 'paid',
        })
        self.order = Order.objects.get()
        self.url = reverse('conference_payment', args=[self.order.conference_registration.payment_token])

    def rpc(self, method, params):
        auth = base64.b64encode(b'Paycom:test-secret').decode()
        return self.client.post(reverse('payme_webhook'), {
            'id': 1, 'method': method, 'params': params,
        }, content_type='application/json', HTTP_AUTHORIZATION=f'Basic {auth}').json()

    def params(self):
        return {'id': 'test-conference-txn', 'time': 1, 'amount': 62500000,
                'account': {'order_id': self.order.pk, 'user_id': self.order.conference_registration_id}}

    def test_price_is_fixed_and_checkout_returns_to_private_conference_status(self):
        self.assertEqual(self.order.amount, Decimal('625000.00'))
        self.assertEqual(self.order.status, 'pending')
        encoded = generate_payme_url(self.order).split('https://checkout.test.paycom.uz/')[1]
        payload = base64.b64decode(encoded).decode()
        self.assertIn(';a=62500000;', payload)
        self.assertIn(f';c=https://example.com{self.url};', payload)
        self.assertContains(self.client.get(self.url), 'Pay with Payme')
        self.assertNotContains(self.client.get(self.url + '?status=paid'), 'Payment confirmed')

    @patch('app.notifications.send_membership_welcome_email_async')
    @patch('app.notifications.send_membership_purchase_notification_async')
    def test_payme_lifecycle_updates_conference_without_membership_notifications(self, purchase, welcome):
        self.assertTrue(self.rpc('CheckPerformTransaction', self.params())['result']['allow'])
        self.assertEqual(self.rpc('CreateTransaction', self.params())['result']['state'], 1)
        self.assertEqual(self.rpc('CreateTransaction', self.params())['result']['state'], 1)
        self.assertEqual(self.rpc('PerformTransaction', {'id': 'test-conference-txn'})['result']['state'], 2)
        self.assertEqual(self.rpc('PerformTransaction', {'id': 'test-conference-txn'})['result']['state'], 2)
        self.assertContains(self.client.get(self.url), 'Payment confirmed')
        self.assertNotContains(self.client.get(self.url), 'Pay with Payme')
        purchase.assert_not_called()
        welcome.assert_not_called()
        self.assertEqual(self.rpc('CancelTransaction', {'id': 'test-conference-txn', 'reason': 1})['result']['state'], -2)
        self.assertContains(self.client.get(self.url), 'Payment cancelled')

    def test_incorrect_amount_account_and_unauthorized_callback_cannot_mark_paid(self):
        self.assertEqual(self.rpc('CheckPerformTransaction', {**self.params(), 'amount': 1})['error']['code'], -31001)
        self.assertEqual(self.rpc('CreateTransaction', {**self.params(), 'amount': 1})['error']['code'], -31001)
        params = self.params()
        params['account']['user_id'] = 99999
        self.assertEqual(self.rpc('CreateTransaction', params)['error']['code'], -31050)
        response = self.client.post(reverse('payme_webhook'), {
            'id': 1, 'method': 'PerformTransaction', 'params': {'id': 'test-conference-txn'},
        }, content_type='application/json')
        self.assertEqual(response.json()['error']['code'], -32504)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    @override_settings(PAYME_CASHBOX_ID='')
    def test_missing_merchant_does_not_show_broken_checkout(self):
        self.assertContains(self.client.get(self.url), 'Online payment is temporarily unavailable')
        self.assertNotContains(self.client.get(self.url), 'Pay with Payme')

    def test_membership_payment_page_cannot_access_conference_order(self):
        self.assertEqual(self.client.get(reverse('membership_payment', args=[self.order.pk])).status_code, 404)
