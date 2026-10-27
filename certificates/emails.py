"""Certificate emails: links to the public download page (no attachments, so sending stays fast)."""
import logging
import os
import uuid

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def portal_base():
    """Public certificate portal, e.g. https://certificates.uztea.uz (local: http://127.0.0.1:8000/certificates)."""
    return os.getenv('CERTIFICATES_BASE_URL', 'https://certificates.uztea.uz').rstrip('/')


def download_url(certificate):
    return f'{portal_base()}/d/{certificate.token}/'


def verify_url(number):
    return f'{portal_base()}/v/{number}/'


def _send(to, subject, html):
    message = EmailMultiAlternatives(subject=subject, body=strip_tags(html), from_email=settings.DEFAULT_FROM_EMAIL, to=[to])
    message.attach_alternative(html, 'text/html')
    message.send(fail_silently=False)


def send_certificate_emails(certificates, user=None):
    """Email each certificate's owner a download link. Returns (sent, skipped, failed)."""
    from workspace.models import MessageLog

    batch = uuid.uuid4()
    sent = skipped = failed = 0
    for cert in certificates:
        person = {'id': cert.pk, 'name': cert.recipient_name}
        subject = f'Your certificate: {cert.event_name}'
        if not cert.email:
            skipped += 1
            MessageLog.objects.create(batch=batch, channel='email', source='certificate', recipient_id=cert.pk,
                                      recipient_name=cert.recipient_name[:255], subject=subject, status='skipped',
                                      error='No email address', sent_by=user)
            continue
        html = render_to_string('certificates/email_certificate.html', {
            'cert': cert, 'download_url': download_url(cert), 'verify_url': verify_url(cert.number)})
        try:
            _send(cert.email, subject, html)
            cert.emailed_at = timezone.now()
            cert.save(update_fields=['emailed_at'])
            status, error = 'sent', ''
            sent += 1
        except Exception as exc:
            logger.warning('Certificate email %s failed: %s', cert.number, exc)
            status, error = 'failed', str(exc)
            failed += 1
        MessageLog.objects.create(batch=batch, channel='email', source='certificate', recipient_id=person['id'],
                                  recipient_name=cert.recipient_name[:255], to=cert.email, subject=subject,
                                  body=f'{cert.number} — {download_url(cert)}', status=status, error=error[:2000],
                                  sent_by=user)
    return sent, skipped, failed


def send_lookup_email(email, certificates, lang='en'):
    """Portal lookup: send the list of someone's certificates to the address on file."""
    html = render_to_string('certificates/email_lookup.html', {
        'items': [{'cert': c, 'download_url': download_url(c)} for c in certificates], 'lang': lang})
    _send(email, 'Your UzTEA certificates', html)
