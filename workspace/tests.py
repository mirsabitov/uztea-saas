from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import Membership, Partner, TeacherBank
from app.payment_status import (
    NO_PAYMENT,
    bulk_membership_payment_status,
    membership_payment_status,
)
from atmos.models import AtmosTransaction
from click.models import Order

SECTION_URLS = [
    'workspace:home', 'workspace:people', 'workspace:teachers_bank', 'workspace:contacts',
    'workspace:forms', 'workspace:form_studio', 'workspace:payments', 'workspace:partners',
    'workspace:settings', 'workspace:tools',
]


def make_membership(**kwargs):
    data = dict(
        full_name='Test Person', email='person@example.org', nationality='Uzbek', phone_number='+998900000000',
        country='Uzbekistan', region_city='Tashkent', position='teacher', institution_name='Example School',
        institution_type='school', experience='3-5', membership_type='teacher', preferred_language='en',
        contact_method='email',
    )
    data.update(kwargs)
    return Membership.objects.create(**data)


class WorkspaceAccessTests(TestCase):
    def test_anonymous_redirects_to_admin_login(self):
        response = self.client.get(reverse('workspace:people'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith(reverse('admin:login')))

    def test_non_staff_user_redirects(self):
        user = User.objects.create_user('member', password='test-password')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('workspace:home')).status_code, 302)

    def test_staff_without_permissions_sees_only_home(self):
        staff = User.objects.create_user('staff', password='test-password', is_staff=True)
        self.client.force_login(staff)
        home = self.client.get(reverse('workspace:home'))
        self.assertEqual(home.status_code, 200)
        self.assertEqual([item['key'] for item in home.context['nav']], ['home'])
        for name in ('workspace:people', 'workspace:payments', 'workspace:partners', 'workspace:settings'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_teachers_bank_permission_does_not_open_members(self):
        staff = User.objects.create_user('tb', password='test-password', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_teacherbank'))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('workspace:teachers_bank')).status_code, 200)
        self.assertEqual(self.client.get(reverse('workspace:people')).status_code, 403)
        member = make_membership()
        self.assertEqual(self.client.get(reverse('workspace:member_profile', args=[member.pk])).status_code, 403)

    def test_view_only_user_gets_no_bulk_actions_or_add_buttons(self):
        staff = User.objects.create_user('viewer', password='test-password', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_membership'))
        self.client.force_login(staff)
        make_membership()
        response = self.client.get(reverse('workspace:people'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['bulk'])
        self.assertIsNone(response.context['add_url'])
        self.assertIsNone(response.context['import_url'])


class WorkspacePagesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.org', 'test-password')
        self.client.force_login(self.admin)
        self.member = make_membership(full_name='Aziza Example', email='aziza@example.org')
        self.pending = make_membership(full_name='Pending Example', email='pending@example.org', is_pending_payment=True)
        TeacherBank.objects.create(full_name='Aziza Example', email='aziza@example.org', source='Import')
        Partner.objects.create(full_name='Partner Example', email='partner@example.org', company_name='Example Org')

    def test_every_section_renders(self):
        for name in SECTION_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for tab in ('orders', 'pending', 'atmos', 'payme', 'promo', 'tools'):
            self.assertEqual(self.client.get(reverse('workspace:payments'), {'tab': tab}).status_code, 200, tab)
        for key in ('event', 'membership', 'feedback', 'blank'):
            self.assertEqual(self.client.get(reverse('workspace:form_studio'), {'template': key}).status_code, 200, key)

    def test_members_and_pending_lists_are_separate(self):
        members = self.client.get(reverse('workspace:people'))
        self.assertContains(members, 'Aziza Example')
        self.assertNotContains(members, 'Pending Example')
        pending = self.client.get(reverse('workspace:people'), {'view': 'pending'})
        self.assertContains(pending, 'Pending Example')
        self.assertNotContains(pending, 'Aziza Example')

    def test_search_by_membership_id(self):
        make_membership(full_name='Other Person', email='other@example.org')
        response = self.client.get(reverse('workspace:people'), {'q': f'UZ{self.member.pk:06d}'})
        self.assertEqual([row['pk'] for row in response.context['rows']], [self.member.pk])

    def test_filters_and_sort(self):
        make_membership(full_name='Student Person', email='s@example.org', membership_type='student', preferred_language='uz')
        response = self.client.get(reverse('workspace:people'), {'type': 'student', 'language': 'uz', 'sort': 'name'})
        self.assertEqual([row['obj'].full_name for row in response.context['rows']], ['Student Person'])
        bad_sort = self.client.get(reverse('workspace:people'), {'sort': 'password'})
        self.assertEqual(bad_sort.context['sort'], '-joined')

    def test_preview_partial_and_profile(self):
        preview = self.client.get(reverse('workspace:member_preview', args=[self.member.pk]))
        self.assertContains(preview, 'Member preview')
        self.assertContains(preview, f'UZ{self.member.pk:06d}')
        self.assertContains(preview, reverse('membership_card', args=[self.member.pk]))
        self.assertNotContains(preview, '<html')
        profile = self.client.get(reverse('workspace:member_profile', args=[self.member.pk]))
        self.assertContains(profile, 'Example School')
        # Same email in Teachers Bank is shown as a hint, not merged.
        self.assertContains(profile, 'Teachers Bank')
        self.assertEqual(TeacherBank.objects.filter(email='aziza@example.org').count(), 1)

    def test_server_rendered_preview_from_query(self):
        response = self.client.get(reverse('workspace:people'), {'preview': self.member.pk})
        self.assertEqual(response.context['preview']['member'], self.member)

    def test_profile_shows_every_model_field(self):
        response = self.client.get(reverse('workspace:member_profile', args=[self.member.pk]))
        labels = {item['label'].lower() for s in response.context['sections'] for item in s['items']}
        shown_elsewhere = {'id', 'payment proof', 'is pending payment', 'created at'}
        for field in Membership._meta.concrete_fields:
            name = field.verbose_name.lower()
            self.assertTrue(name in labels or name in shown_elsewhere, name)

    def test_all_contacts_lists_every_source_without_merging(self):
        response = self.client.get(reverse('workspace:contacts'))
        rows = response.context['page'].object_list
        aziza = [r for r in rows if r['email'] == 'aziza@example.org']
        self.assertEqual(sorted(r['source'] for r in aziza), ['Member', 'Teachers Bank'])
        self.assertIn('Teachers Bank', next(r for r in aziza if r['source'] == 'Member')['also_in'])

    def test_bulk_actions_post_to_admin_changelist(self):
        members = self.client.get(reverse('workspace:people'))
        self.assertEqual(members.context['bulk']['url'], reverse('admin:app_membership_changelist'))
        pending = self.client.get(reverse('workspace:people'), {'view': 'pending'})
        self.assertEqual(pending.context['bulk']['url'], reverse('admin:app_pendingpayment_changelist'))

    def test_workspace_bulk_form_runs_admin_action(self):
        response = self.client.post(reverse('admin:app_pendingpayment_changelist'), {
            'action': 'return_to_memberships', 'index': 0, 'select_across': 0,
            '_selected_action': [self.pending.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_pending_payment)

    @override_settings(PAYME_SECRET_KEY='very-secret-value', PAYME_CASHBOX_ID='cashbox-test')
    def test_settings_never_show_secret_values(self):
        response = self.client.get(reverse('workspace:settings'))
        self.assertContains(response, 'Payme')
        self.assertNotContains(response, 'very-secret-value')
        self.assertNotContains(response, 'cashbox-test')

    def test_legacy_public_pages_still_work(self):
        self.client.logout()
        for name in ('membership_form', 'conference_register', 'anniversary_register'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


class PaymentStatusTests(TestCase):
    def test_bulk_matches_single(self):
        none = make_membership(email='a@example.org')
        paid = make_membership(email='b@example.org')
        Order.objects.create(membership=paid, amount=Decimal('100'), status='paid')
        failed = make_membership(email='c@example.org')
        Order.objects.create(membership=failed, amount=Decimal('100'), status='failed')
        atmos = make_membership(email='d@example.org')
        order = Order.objects.create(membership=atmos, amount=Decimal('100'), status='paid')
        AtmosTransaction.objects.create(transaction_id='t-1', account=str(order.pk), amount=10000, status='OTP_SENT')

        members = [none, paid, failed, atmos]
        bulk = bulk_membership_payment_status(members)
        self.assertEqual(bulk, {m.pk: membership_payment_status(m) for m in members})
        self.assertEqual(bulk[none.pk], NO_PAYMENT)
        self.assertEqual(bulk[paid.pk], 'SUCCESS')
        self.assertEqual(bulk[failed.pk], 'FAILED')
        self.assertEqual(bulk[atmos.pk], 'OTP_SENT')  # latest Atmos transaction wins, as in the admin


class DemoDataCommandTests(TestCase):
    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command('workspace_demo_data')
