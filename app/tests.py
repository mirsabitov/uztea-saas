from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from tablib import Dataset

from .admin import (
    CustomMembershipEmailForm,
    MembershipAdmin,
    PartnerResource,
    TeacherBankResource,
)
from .models import Partner, TeacherBank


class MembershipRevenueTests(TestCase):
    def test_conference_payments_are_excluded_from_membership_revenue(self):
        from unittest.mock import patch
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from import_export.admin import ImportExportModelAdmin
        from .models import ConferenceRegistration, Membership
        from click.models import Order

        membership = Membership.objects.create(full_name='Member', membership_type='teacher')
        Order.objects.create(membership=membership, amount=250000, status='paid')
        Order.objects.create(membership=membership, amount=99000, status='pending')
        registration = ConferenceRegistration.objects.create(full_name='Conference attendee')
        conference_order = Order.objects.create(
            conference_registration=registration, amount=625000, status='paid',
        )
        model_admin = MembershipAdmin(Membership, AdminSite())
        request = RequestFactory().get('/admin/app/membership/')
        with patch.object(ImportExportModelAdmin, 'changelist_view') as parent_view:
            model_admin.changelist_view(request)
        cards = parent_view.call_args.kwargs['extra_context']['membership_payment_cards']
        total = next(card for card in cards if card.get('is_total'))
        self.assertEqual(total['total_display'], '250 000')
        self.assertEqual(total['payment_count'], 1)
        conference_order.refresh_from_db()
        self.assertEqual(conference_order.status, 'paid')

        Order.objects.filter(membership=membership).delete()
        with patch.object(ImportExportModelAdmin, 'changelist_view') as parent_view:
            model_admin.changelist_view(request)
        cards = parent_view.call_args.kwargs['extra_context']['membership_payment_cards']
        total = next(card for card in cards if card.get('is_total'))
        self.assertEqual(total['total_display'], '0')
        self.assertEqual(total['payment_count'], 0)


class CustomMembershipEmailFormTests(TestCase):
    def form_with_attachment(self, attachment):
        return CustomMembershipEmailForm(
            data={
                'sender': 'uztea',
                'template': 'custom',
                'subject': 'Test subject',
                'body': '<p>Test message</p>',
            },
            files={'attachments': attachment},
        )

    def test_accepts_attachment_of_exactly_five_mb(self):
        attachment = SimpleUploadedFile('allowed.pdf', b'x' * (5 * 1024 * 1024))

        form = self.form_with_attachment(attachment)

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_attachment_larger_than_five_mb(self):
        attachment = SimpleUploadedFile('too-large.pdf', b'x' * (5 * 1024 * 1024 + 1))

        form = self.form_with_attachment(attachment)

        self.assertFalse(form.is_valid())
        self.assertIn('too-large.pdf is larger than the maximum allowed size of 5 MB.', form.errors['attachments'])

    def test_matched_expo_template_contains_brand_and_recipient(self):
        html = MembershipAdmin._wrap_custom_email(
            '<p>Invitation details</p>',
            'matched_expo',
            recipient_name='Jane & John',
        )

        self.assertIn('cid:matchedexpo-header', html)
        self.assertIn('@media only screen and (max-width:600px)', html)
        self.assertIn('Dear Jane &amp; John,', html)
        self.assertIn('https://t.me/matchedexpo', html)
        self.assertIn('https://www.youtube.com/@MatchEDExpo', html)

    def test_uztea_branded_template_contains_recipient_and_footer(self):
        html = MembershipAdmin._wrap_custom_email(
            '<p>UzTEA update</p>', 'uztea_brand', recipient_name='Jane Doe'
        )

        self.assertIn('Dear Jane Doe,', html)
        self.assertIn('Stay connected with UzTEA', html)
        self.assertIn('cid:uztea-logo', html)

    def test_uztea_simple_template_has_compact_footer(self):
        html = MembershipAdmin._wrap_custom_email(
            '<p>Short update</p>', 'uztea_simple', recipient_name='Jane Doe'
        )

        self.assertIn('Dear Jane Doe,', html)
        self.assertIn('Stay connected with UzTEA', html)
        self.assertIn('info@uztea.uz', html)


class ContactImportDeduplicationTests(TestCase):
    def test_partner_import_skips_duplicate_emails_in_database_and_file(self):
        Partner.objects.create(full_name='Existing', email='existing@example.com')
        dataset = Dataset(
            ('Existing duplicate', ' EXISTING@EXAMPLE.COM ', '', '', '', '', ''),
            ('First', ' Same@Example.com ', '', '', '', '', ''),
            ('Second', 'same@example.com', '', '', '', '', ''),
            headers=(
                'full_name', 'email', 'phone_number', 'position',
                'company_name', 'country', 'source',
            ),
        )

        result = PartnerResource().import_data(dataset, dry_run=False, raise_errors=True)

        self.assertEqual(result.totals['new'], 1)
        self.assertEqual(result.totals['skip'], 2)
        self.assertEqual(Partner.objects.get(full_name='First').email, 'same@example.com')

    def test_teacher_import_keeps_rows_with_empty_email(self):
        dataset = Dataset(
            ('First', '', '', ''),
            ('Second', '', '', ''),
            headers=('full_name', 'email', 'phone_number', 'source'),
        )

        result = TeacherBankResource().import_data(
            dataset, dry_run=False, raise_errors=True
        )

        self.assertEqual(result.totals['new'], 2)
        self.assertEqual(TeacherBank.objects.count(), 2)
