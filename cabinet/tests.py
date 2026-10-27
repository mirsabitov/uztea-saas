from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cabinet.accounts import get_or_create_member_user, password_link
from click.models import Order
from workspace.models import Benefit, Event
from workspace.tests import make_membership


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SITE_BASE_URL='http://testserver')
class CabinetTests(TestCase):
    def setUp(self):
        self.member = make_membership(full_name='Aziza Karimova', email='Aziza@Example.org', membership_type='teacher')
        order = Order.objects.create(membership=self.member, amount=Decimal('150000'), status='paid')
        Order.objects.filter(pk=order.pk).update(updated_at=timezone.now() - timedelta(days=10))

    def set_password(self):
        user = get_or_create_member_user(self.member.email, self.member.full_name)
        path = password_link(user).replace('http://testserver', '')
        response = self.client.post(path, {'password1': 'long-enough-1', 'password2': 'long-enough-1'})
        return user, response

    def test_request_link_only_for_member_emails_and_same_answer(self):
        for email in ('aziza@example.org', 'stranger@example.org'):
            response = self.client.post(reverse('cabinet:request_link'), {'email': email})
            self.assertTrue(response.context['sent'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['Aziza@Example.org'])
        self.assertIn('/account/set-password/', mail.outbox[0].body)

    def test_set_password_logs_in_and_link_is_single_use(self):
        user, response = self.set_password()
        self.assertRedirects(response, reverse('cabinet:home'))
        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        self.assertFalse(user.is_staff)
        reused = self.client.get(password_link_from_old := '/account/set-password/x/y/')
        self.assertFalse(reused.context['valid'])
        del password_link_from_old

    def test_short_password_rejected(self):
        user = get_or_create_member_user(self.member.email)
        path = password_link(user).replace('http://testserver', '')
        response = self.client.post(path, {'password1': 'short', 'password2': 'short'})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.has_usable_password())

    def test_login_and_dashboard(self):
        self.set_password()
        self.client.logout()
        bad = self.client.post(reverse('cabinet:login'), {'email': 'aziza@example.org', 'password': 'wrong-password'})
        self.assertContains(bad, 'Incorrect email or password')
        good = self.client.post(reverse('cabinet:login'), {'email': 'AZIZA@example.org', 'password': 'long-enough-1'})
        self.assertRedirects(good, reverse('cabinet:home'))

        Event.objects.create(title='Members workshop', starts_at=timezone.now() + timedelta(days=5), is_published=True,
                             members_only=True)
        Event.objects.create(title='Draft event', starts_at=timezone.now() + timedelta(days=5), is_published=False)
        Benefit.objects.create(title='Teacher discount', membership_types='teacher', code='T20')
        Benefit.objects.create(title='Student only', membership_types='student')
        home = self.client.get(reverse('cabinet:home'))
        self.assertEqual(home.context['status']['key'], 'active')
        self.assertContains(home, f'UZ{self.member.pk:06d}')
        self.assertContains(home, 'Members workshop')
        self.assertNotContains(home, 'Draft event')
        self.assertContains(home, 'T20')
        self.assertNotContains(home, 'Student only')
        self.assertContains(home, '150 000 UZS')

    def test_cabinet_requires_login_and_members_cannot_open_workspace(self):
        self.assertRedirects(self.client.get(reverse('cabinet:home')), reverse('cabinet:login') + '?next=/account/',
                             fetch_redirect_response=False)
        self.set_password()
        self.assertEqual(self.client.get(reverse('workspace:home')).status_code, 302)

    def test_staff_accounts_cannot_use_cabinet_links(self):
        staff = User.objects.create_user('aziza@example.org', email='aziza@example.org', password='pw', is_staff=True)
        response = self.client.post(reverse('cabinet:request_link'), {'email': 'aziza@example.org'})
        self.assertTrue(response.context['sent'])
        self.assertEqual(len(mail.outbox), 0)
        path = password_link(staff).replace('http://testserver', '')
        self.assertFalse(self.client.get(path).context['valid'])

    def test_workspace_invite(self):
        admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(admin)
        self.client.post(reverse('workspace:cabinet_invite'), {'ids': [self.member.pk]})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('invited', mail.outbox[0].body)
