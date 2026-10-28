from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Permission, User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app import membership_lifecycle as lifecycle
from app.models import Partner
from atmos.models import AtmosTransaction
from click.models import Order
from payme.models import PaymeTransaction
from workspace import sms
from workspace.models import MessageLog
from workspace.tests import make_membership


def paid_order(member, days_ago, status='paid'):
    order = Order.objects.create(membership=member, amount=Decimal('100000'), status=status)
    when = timezone.now() - timedelta(days=days_ago)
    Order.objects.filter(pk=order.pk).update(created_at=when, updated_at=when)
    return order


class LifecycleTests(TestCase):
    def test_statuses_follow_the_approved_rules(self):
        active = make_membership(email='a@example.org')
        paid_order(active, 10)
        due = make_membership(email='b@example.org')
        paid_order(due, 350)
        expired = make_membership(email='c@example.org')
        paid_order(expired, 400)
        pending = make_membership(email='d@example.org')
        paid_order(pending, 5, status='pending')
        no_record = make_membership(email='e@example.org')

        result = lifecycle.bulk_status([active, due, expired, pending, no_record])
        self.assertEqual(result[active.pk]['key'], lifecycle.ACTIVE)
        self.assertEqual(result[due.pk]['key'], lifecycle.RENEWAL_DUE)
        self.assertEqual(result[expired.pk]['key'], lifecycle.EXPIRED)
        self.assertEqual(result[pending.pk]['key'], lifecycle.PENDING)
        self.assertEqual(result[no_record.pk]['key'], lifecycle.NO_RECORD)
        self.assertEqual((result[active.pk]['valid_until'] - result[active.pk]['paid_at']).days, 365)

    def test_latest_payment_renews_and_provider_dates_win(self):
        member = make_membership()
        paid_order(member, 400)  # old payment, expired on its own
        renewal = paid_order(member, 300, status='processing')
        AtmosTransaction.objects.create(transaction_id='r-1', account=str(renewal.pk), amount=1, status='SUCCESS')
        AtmosTransaction.objects.filter(transaction_id='r-1').update(updated_at=timezone.now() - timedelta(days=20))
        status = lifecycle.membership_status(member)
        self.assertEqual(status['key'], lifecycle.ACTIVE)
        self.assertEqual((timezone.now() - status['paid_at']).days, 20)

        payme_order = paid_order(member, 2)
        PaymeTransaction.objects.create(transaction_id='p-1', order=payme_order, amount=1, state=2,
                                        performed_at=timezone.now() - timedelta(days=1))
        self.assertEqual((timezone.now() - lifecycle.membership_status(member)['paid_at']).days, 1)

    def test_people_status_filters_and_sort(self):
        admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(admin)
        active = make_membership(full_name='Active One', email='a@example.org')
        paid_order(active, 10)
        due = make_membership(full_name='Due One', email='b@example.org')
        paid_order(due, 350)
        make_membership(full_name='Never Paid', email='c@example.org')
        names = lambda r: [row['obj'].full_name for row in r.context['rows']]
        self.assertEqual(sorted(names(self.client.get(reverse('workspace:people'), {'status': 'active'}))),
                         ['Active One', 'Due One'])
        self.assertEqual(names(self.client.get(reverse('workspace:people'), {'status': 'renewal_due'})), ['Due One'])
        self.assertEqual(names(self.client.get(reverse('workspace:people'), {'status': 'no_record'})), ['Never Paid'])
        self.assertEqual(names(self.client.get(reverse('workspace:people'), {'sort': 'renewal'})),
                         ['Due One', 'Active One', 'Never Paid'])

    def test_institution_members_are_listed_as_people(self):
        admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(admin)
        inst = make_membership(full_name='School 1', email='s@example.org', membership_type='institutional',
                               member_2_name='Teacher Two', member_2_email='two@example.org')
        rows = self.client.get(reverse('workspace:contacts'), {'source': 'institution_member'}).context['page'].object_list
        self.assertEqual([(r['name'], r['email']) for r in rows], [('Teacher Two', 'two@example.org')])
        profile = self.client.get(reverse('workspace:member_profile', args=[inst.pk]))
        self.assertContains(profile, 'Teacher Two')


class EskizClientTests(TestCase):
    def test_normalize_phone(self):
        self.assertEqual(sms.normalize_phone('+998 (90) 123-45-67'), '998901234567')
        self.assertEqual(sms.normalize_phone('90 123 45 67'), '998901234567')
        self.assertIsNone(sms.normalize_phone('+1 202 555 0101'))
        self.assertIsNone(sms.normalize_phone(''))

    def test_sms_parts(self):
        self.assertEqual(sms.sms_parts('a' * 160), 1)
        self.assertEqual(sms.sms_parts('a' * 161), 2)
        self.assertEqual(sms.sms_parts('Салом'), 1)
        self.assertEqual(sms.sms_parts('С' * 71), 2)

    @mock.patch.dict('os.environ', {'ESKIZ_EMAIL': 'e@example.org', 'ESKIZ_PASSWORD': 'pw', 'ESKIZ_FROM': '4546'})
    @mock.patch('workspace.sms.requests.post')
    def test_send_logs_in_and_retries_once_on_401(self, post):
        sms._token.update(value='old-token', at=1e12)
        login = mock.Mock(status_code=200, json=lambda: {'data': {'token': 'new-token'}})
        unauthorized = mock.Mock(status_code=401, json=lambda: {})
        ok = mock.Mock(status_code=200, json=lambda: {'id': 'abc-1', 'status': 'waiting'})
        post.side_effect = [unauthorized, login, ok]
        self.assertEqual(sms.send_sms('998901234567', 'Hello'), 'abc-1')
        self.assertEqual(post.call_args.kwargs['headers'], {'Authorization': 'Bearer new-token'})
        self.assertEqual(post.call_args.kwargs['data']['mobile_phone'], '998901234567')


class ComposeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(self.admin)
        self.a = make_membership(full_name='Aziza', email='aziza@example.org', phone_number='+998901112233',
                                 agree_communication=True)
        self.b = make_membership(full_name='Bekzod', email='', phone_number='12345')
        paid_order(self.a, 10)
        self.url = reverse('workspace:message_compose') + '?source=member'

    def send(self, **data):
        payload = {'step': 'send', 'source': 'member', 'ids': [self.a.pk, self.b.pk], 'confirm': 'on',
                   'sender': 'uztea', 'template': 'uztea_simple'}
        payload.update(data)
        return self.client.post(self.url, payload)

    def test_compose_page_from_bulk_selection(self):
        response = self.client.post(self.url + '&channel=sms', {'_selected_action': [self.a.pk, self.b.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 2)
        self.assertEqual(response.context['with_phone'], 1)
        self.assertEqual(response.context['with_email'], 1)

    @override_settings(DEBUG=True)
    @mock.patch.dict('os.environ', {'ESKIZ_EMAIL': '', 'ESKIZ_PASSWORD': ''})
    def test_sms_test_mode_logs_without_sending(self):
        with mock.patch('workspace.sms.requests.post') as post:
            response = self.send(channel='sms', sms_text='Hi {name}, ID {membership_id}')
        post.assert_not_called()
        self.assertEqual(response.status_code, 302)
        logs = {l.recipient_name: l for l in MessageLog.objects.all()}
        self.assertEqual(logs['Aziza'].status, MessageLog.TEST)
        self.assertEqual(logs['Aziza'].body, f'Hi Aziza, ID UZ{self.a.pk:06d}')
        self.assertEqual(logs['Bekzod'].status, MessageLog.SKIPPED)

    @mock.patch.dict('os.environ', {'ESKIZ_EMAIL': 'e@example.org', 'ESKIZ_PASSWORD': 'pw'})
    @mock.patch('workspace.sms.send_sms', return_value='eskiz-77')
    def test_sms_live_sends_to_valid_numbers(self, send_sms):
        self.send(channel='sms', sms_text='Hello {name}')
        send_sms.assert_called_once_with('998901112233', 'Hello Aziza')
        log = MessageLog.objects.get(recipient_name='Aziza')
        self.assertEqual((log.status, log.provider_id, log.sent_by), (MessageLog.SENT, 'eskiz-77', self.admin))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_email_uses_admin_templates(self):
        self.send(channel='email', subject='Hello {name}', body='Your membership is valid until {valid_until}.')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['aziza@example.org'])
        self.assertEqual(mail.outbox[0].subject, 'Hello Aziza')
        self.assertEqual(MessageLog.objects.get(recipient_name='Bekzod').status, MessageLog.SKIPPED)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_unsubscribed_members_get_no_news_email(self):
        self.a.agree_communication = False
        self.a.save()
        self.send(channel='email', subject='News', body='Hello')
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(MessageLog.objects.get(recipient_name='Aziza').error, 'Unsubscribed from UzTEA emails')

    def test_confirmation_required(self):
        response = self.send(channel='sms', sms_text='Hi', confirm='')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MessageLog.objects.exists())

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(self.url, {'step': 'send', 'channel': 'sms', 'sms_text': 'x', 'confirm': 'on',
                                          'ids': [self.a.pk]})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MessageLog.objects.exists())

    def test_permissions(self):
        viewer = User.objects.create_user('viewer', password='pw', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_membership'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.url + f'&ids={self.a.pk}').status_code, 403)
        people = self.client.get(reverse('workspace:people'))
        self.assertIsNone(people.context['message_url'])

        sender = User.objects.create_user('sender', password='pw', is_staff=True)
        sender.user_permissions.add(Permission.objects.get(codename='add_messagelog'),
                                    Permission.objects.get(codename='view_partner'))
        self.client.force_login(sender)
        # may send to partners, not to members
        self.assertEqual(self.client.get(self.url + f'&ids={self.a.pk}').status_code, 403)
        partner = Partner.objects.create(full_name='P', email='p@example.org')
        partner_url = reverse('workspace:message_compose') + f'?source=partner&ids={partner.pk}'
        self.assertEqual(self.client.get(partner_url).status_code, 200)

    def test_history_lists_messages(self):
        MessageLog.objects.create(batch='00000000-0000-0000-0000-000000000001', channel='sms', source='member',
                                  recipient_id=self.a.pk, recipient_name='Aziza', to='998901112233',
                                  body='Hi', status=MessageLog.SENT)
        response = self.client.get(reverse('workspace:messages'))
        self.assertContains(response, 'Aziza')
        profile = self.client.get(reverse('workspace:member_profile', args=[self.a.pk]))
        self.assertContains(profile, 'SMS sent')


class WebsiteTests(TestCase):
    def test_website_placeholder_for_staff(self):
        staff = User.objects.create_user('staff', password='pw', is_staff=True)
        self.client.force_login(staff)
        self.assertContains(self.client.get(reverse('workspace:website')), 'Next phase')
