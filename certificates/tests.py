import io
import json
from unittest import mock

from django.contrib.auth.models import Permission, User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from certificates import recipients as rcp
from certificates.models import Certificate, CertificateSequence, CertificateTemplate
from certificates.views_workspace import _clean_design
from workspace.tests import make_membership

FAKE_PDF = b'%PDF-1.4 fake'


def make_template(**kw):
    data = dict(name='TESOL 2026', event_name='TESOL Uzbekistan 2026', date_text='12 March 2026', signer_name='Signer')
    data.update(kw)
    return CertificateTemplate.objects.create(**data)


class NumberingTests(TestCase):
    def test_numbers_are_sequential_per_year_and_unique(self):
        self.assertEqual(CertificateSequence.next_number(2026), 'UZTEA-2026-000001')
        self.assertEqual(CertificateSequence.next_number(2026), 'UZTEA-2026-000002')
        self.assertEqual(CertificateSequence.next_number(2027), 'UZTEA-2027-000001')

    def test_certificate_gets_number_and_event_from_template(self):
        cert = Certificate.objects.create(template=make_template(), recipient_name='Aziza')
        self.assertRegex(cert.number, r'^UZTEA-\d{4}-000001$')
        self.assertEqual(cert.event_name, 'TESOL Uzbekistan 2026')


class RecipientParsingTests(TestCase):
    def test_csv_with_header_links_members(self):
        member = make_membership(email='aziza@example.org')
        upload = SimpleUploadedFile('list.csv', b'Name,Email\nAziza K,aziza@example.org\nBekzod,not-an-email\n,x@example.org\n')
        rows, problems = rcp.normalise(rcp.parse_upload(upload))
        self.assertEqual([r['name'] for r in rows], ['Aziza K', 'Bekzod'])
        self.assertEqual(rows[0]['membership_id'], member.pk)
        self.assertEqual(rows[1]['email'], '')
        self.assertEqual(len(problems), 2)  # invalid email + missing name

    def test_xlsx_and_paste(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(['Full name', 'E-mail'])
        wb.active.append(['Diyor T', 'diyor@example.org'])
        buf = io.BytesIO()
        wb.save(buf)
        rows, _ = rcp.normalise(rcp.parse_upload(SimpleUploadedFile('list.xlsx', buf.getvalue())))
        self.assertEqual(rows, [{'name': 'Diyor T', 'email': 'diyor@example.org', 'membership_id': None}])
        rows, _ = rcp.normalise(rcp.parse_paste('Nilufar S; nilufar@example.org\nMalika\tmalika@example.org'))
        self.assertEqual([r['email'] for r in rows], ['nilufar@example.org', 'malika@example.org'])

    def test_membership_id_column_fills_name_and_email(self):
        member = make_membership(full_name='Rustam U', email='rustam@example.org')
        rows, _ = rcp.normalise([{'name': '', 'email': '', 'membership_id': f'UZ{member.pk:06d}'}])
        self.assertEqual(rows, [{'name': 'Rustam U', 'email': 'rustam@example.org', 'membership_id': member.pk}])


class DesignCleaningTests(TestCase):
    def test_unknown_keys_and_bad_values_are_dropped(self):
        raw = json.dumps([
            {'id': 'a', 'type': 'text', 'text': 'Hi', 'x': 500, 'size': 99, 'color': 'red;background:url(x)', 'evil': 1},
            {'id': 'b', 'type': 'image', 'source': '../../etc/passwd'},
            {'id': 'c', 'type': 'image', 'source': 'stamp', 'w': 10},
        ])
        clean = _clean_design(raw)
        self.assertEqual(clean[0]['x'], 100)
        self.assertEqual(clean[0]['size'], 12)
        self.assertEqual(clean[0]['color'], '#222e50')
        self.assertNotIn('evil', clean[0])
        self.assertEqual(clean[1]['type'], 'text')  # unknown image source is not trusted as an image
        self.assertEqual(clean[2], {'id': 'c', 'x': 50.0, 'y': 50.0, 'w': 10.0, 'type': 'image', 'source': 'stamp'})
        self.assertIsNone(_clean_design('not json'))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class WorkspaceFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.org', 'pw')
        self.client.force_login(self.admin)
        self.template = make_template()

    def test_issue_to_members_numbers_and_emails(self):
        a = make_membership(full_name='Aziza', email='aziza@example.org')
        b = make_membership(full_name='Bekzod', email='')
        page = self.client.post(reverse('workspace:cert_issue') + '?source=member', {'_selected_action': [a.pk, b.pk]})
        rows = page.context['rows']
        self.assertEqual(len(rows), 2)
        response = self.client.post(reverse('workspace:cert_issue'), {
            'step': 'issue', 'template': self.template.pk, 'rows': json.dumps(rows), 'source': 'member',
            'send_email': 'on', 'skip_existing': 'on'})
        self.assertEqual(response.status_code, 302)
        certs = Certificate.objects.order_by('number')
        self.assertEqual(certs.count(), 2)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(certs.get(recipient_name='Aziza').token), mail.outbox[0].body)
        # Issuing again skips people who already have this certificate
        self.client.post(reverse('workspace:cert_issue'), {
            'step': 'issue', 'template': self.template.pk, 'rows': json.dumps(rows), 'skip_existing': 'on'})
        self.assertEqual(Certificate.objects.count(), 2)

    def test_designer_saves_layout_and_rejects_viewers(self):
        design = [{'id': 'name', 'type': 'text', 'text': '{name}', 'x': 40, 'y': 50, 'w': 80, 'size': 4}]
        self.client.post(reverse('workspace:cert_designer', args=[self.template.pk]), {
            'name': 'Renamed', 'event_name': 'E', 'signer_title': 'President', 'orientation': 'portrait',
            'accent_color': '#123456', 'design': json.dumps(design), 'is_active': 'on'})
        self.template.refresh_from_db()
        self.assertEqual((self.template.name, self.template.orientation), ('Renamed', 'portrait'))
        self.assertEqual(self.template.design[0]['x'], 40)

        viewer = User.objects.create_user('v', password='pw', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_certificatetemplate'))
        self.client.force_login(viewer)
        self.client.post(reverse('workspace:cert_designer', args=[self.template.pk]), {'name': 'Hacked', 'design': '[]'})
        self.template.refresh_from_db()
        self.assertEqual(self.template.name, 'Renamed')
        self.assertEqual(self.client.get(reverse('workspace:cert_issue')).status_code, 403)

    def test_revoke(self):
        cert = Certificate.objects.create(template=self.template, recipient_name='A')
        self.client.post(reverse('workspace:cert_action', args=[cert.pk]), {'action': 'revoke', 'next': 'https://evil.example/'})
        cert.refresh_from_db()
        self.assertEqual(cert.status, Certificate.REVOKED)

    def test_render_html_has_values(self):
        from certificates.render import render_html
        cert = Certificate.objects.create(template=self.template, recipient_name='Aziza <b>K</b>')
        html = render_html(self.template, cert)
        self.assertIn('Aziza &lt;b&gt;K&lt;/b&gt;', html)
        self.assertIn(cert.number, html)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalTests(TestCase):
    def setUp(self):
        self.template = make_template()
        self.member = make_membership(full_name='Aziza', email='aziza@example.org')
        self.cert = Certificate.objects.create(template=self.template, recipient_name='Aziza', email='aziza@example.org',
                                               membership=self.member)

    def test_lookup_never_shows_results_and_emails_the_owner(self):
        url = reverse('certs:home')
        for query in ('aziza@example.org', f'UZ{self.member.pk:06d}', 'nobody@example.org'):
            response = self.client.post(url, {'query': query})
            self.assertTrue(response.context['sent'])
            self.assertNotContains(response, self.cert.number)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({tuple(m.to) for m in mail.outbox}, {('aziza@example.org',)})

    def test_verify_and_download(self):
        ok = self.client.get(reverse('certs:verify', args=[self.cert.number]))
        self.assertContains(ok, 'Aziza')
        self.assertNotContains(ok, 'aziza@example.org')
        self.assertEqual(self.client.get(reverse('certs:verify', args=['UZTEA-2026-999999'])).status_code, 404)
        with mock.patch('certificates.views_public.certificate_pdf', return_value=FAKE_PDF):
            response = self.client.get(reverse('certs:download', args=[self.cert.token]))
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.cert.status = Certificate.REVOKED
        self.cert.save()
        self.assertEqual(self.client.get(reverse('certs:download', args=[self.cert.token])).status_code, 410)

    @override_settings(ALLOWED_HOSTS=['certificates.uztea.uz'])
    def test_subdomain_is_routed_to_portal(self):
        response = self.client.get(f'/v/{self.cert.number}/', HTTP_HOST='certificates.uztea.uz')
        self.assertContains(response, 'Aziza')
