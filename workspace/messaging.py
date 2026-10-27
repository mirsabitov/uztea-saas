"""Send SMS (Eskiz) and email to people chosen in the workspace, and log every attempt.

Email reuses the admin composer's templates and senders (MembershipAdmin helpers),
so messages look the same whichever screen sent them.
"""
import logging
import uuid
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone
from django.utils.html import escape, linebreaks, strip_tags

from app.models import AnniversaryRegistration, ConferenceRegistration, Membership, Partner, TeacherBank

from . import sms
from .access import can
from .models import MessageLog

logger = logging.getLogger(__name__)

MAX_RECIPIENTS = 500

# key: (label, model, view permissions (any), phone field)
SOURCES = {
    'member': ('Members', Membership, ('app.view_membership', 'app.view_pendingpayment'), 'phone_number'),
    'teachers_bank': ('Teachers Bank', TeacherBank, ('app.view_teacherbank',), 'phone_number'),
    'partner': ('Partners', Partner, ('app.view_partner',), 'phone_number'),
    'tesol': ('TESOL Conference', ConferenceRegistration, ('app.view_conferenceregistration',), 'mobile_phone'),
    'anniversary': ('30th Anniversary', AnniversaryRegistration, ('app.view_anniversaryregistration',), 'phone_number'),
}

PLACEHOLDERS = [('{name}', 'Full name'), ('{membership_id}', 'Membership ID (members)'),
                ('{valid_until}', 'Valid until (members)')]


def can_send(user, source=None):
    if not user.has_perm('workspace.add_messagelog'):
        return False
    return source is None or (source in SOURCES and can(user, *SOURCES[source][2]))


def sms_mode():
    """'live' when Eskiz is configured, 'test' on a local DEBUG server, otherwise 'off'."""
    if sms.is_configured():
        return 'live'
    return 'test' if settings.DEBUG else 'off'


def email_is_console():
    return settings.EMAIL_BACKEND.endswith(('console.EmailBackend', 'locmem.EmailBackend', 'dummy.EmailBackend'))


def parse_ids(values):
    ids = []
    for value in values:
        for part in str(value).split(','):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
    return list(dict.fromkeys(ids))


def recipients(source, ids):
    """[{'id', 'name', 'phone', 'email', 'obj'}] in name order."""
    _label, model, _perms, phone_field = SOURCES[source]
    objs = list(model.objects.filter(pk__in=ids).order_by('full_name', 'pk')[:MAX_RECIPIENTS])
    statuses = {}
    if model is Membership:
        from app import membership_lifecycle as lifecycle
        statuses = lifecycle.bulk_status(objs)
    out = []
    for obj in objs:
        phone_raw = getattr(obj, phone_field, '') or ''
        person = {
            'id': obj.pk, 'obj': obj, 'name': obj.full_name or obj.email or f'#{obj.pk}',
            'phone_raw': phone_raw, 'phone': sms.normalize_phone(phone_raw),
            'email': (obj.email or '').strip(), 'values': {},
        }
        if model is Membership:
            person['unsubscribed'] = not obj.agree_communication
            valid_until = statuses[obj.pk]['valid_until']
            person['values'] = {'{membership_id}': f'UZ{obj.pk:06d}',
                                '{valid_until}': timezone.localtime(valid_until).strftime('%d.%m.%Y') if valid_until else ''}
        out.append(person)
    return out


def personalise(text, person):
    values = {'{name}': person['name'], **person.get('values', {})}
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def _log(batch, channel, source, person, user, status, subject='', body='', provider_id='', error=''):
    return MessageLog.objects.create(
        batch=batch, channel=channel, source=source, recipient_id=person['id'], recipient_name=person['name'][:255],
        to=(person['phone'] if channel == MessageLog.CHANNEL_SMS else person['email']) or '',
        subject=subject[:255], body=body, status=status, provider_id=provider_id, error=error[:2000], sent_by=user,
    )


def send_sms_batch(user, source, people, text):
    batch, mode = uuid.uuid4(), sms_mode()
    if mode == 'off':
        raise sms.EskizError('Eskiz is not configured on this server.')
    for person in people:
        body = personalise(text, person)
        if not person['phone']:
            _log(batch, MessageLog.CHANNEL_SMS, source, person, user, MessageLog.SKIPPED, body=body,
                 error='No valid Uzbek mobile number' + (f" ({person['phone_raw']})" if person['phone_raw'] else ''))
            continue
        if mode == 'test':
            _log(batch, MessageLog.CHANNEL_SMS, source, person, user, MessageLog.TEST, body=body)
            continue
        try:
            provider_id = sms.send_sms(person['phone'], body)
            _log(batch, MessageLog.CHANNEL_SMS, source, person, user, MessageLog.SENT, body=body, provider_id=provider_id)
        except Exception as exc:  # one failure must not stop the rest
            logger.warning('SMS to %s #%s failed: %s', source, person['id'], exc)
            _log(batch, MessageLog.CHANNEL_SMS, source, person, user, MessageLog.FAILED, body=body, error=str(exc))
    return batch


def _email_connection(sender):
    if sender == 'matched_expo':
        options = {
            'backend': settings.MATCHED_EXPO_EMAIL_BACKEND, 'host': settings.MATCHED_EXPO_EMAIL_HOST,
            'port': settings.MATCHED_EXPO_EMAIL_PORT, 'username': settings.MATCHED_EXPO_EMAIL_HOST_USER,
            'password': settings.MATCHED_EXPO_EMAIL_HOST_PASSWORD, 'use_tls': settings.MATCHED_EXPO_EMAIL_USE_TLS,
            'use_ssl': settings.MATCHED_EXPO_EMAIL_USE_SSL, 'timeout': settings.MATCHED_EXPO_EMAIL_TIMEOUT,
        }
        return get_connection(fail_silently=False, **options), settings.MATCHED_EXPO_DEFAULT_FROM_EMAIL
    return get_connection(fail_silently=False), settings.DEFAULT_FROM_EMAIL


def body_to_html(text, is_html):
    return text if is_html else linebreaks(escape(text))


def send_email_batch(user, source, people, *, subject, body, is_html, sender, template, attachments=()):
    """Same look as the admin composer: its wrapper templates and inline logos."""
    from app.admin import MembershipAdmin
    from app.views import get_uztea_email_logo_bytes

    batch = uuid.uuid4()
    inline_images = []
    if template == 'matched_expo':
        inline_images.append(('matchedexpo-header', 'matchedexpo-email-header.png',
                              (settings.BASE_DIR / 'static' / 'images' / 'matchedexpo-email-header.png').read_bytes()))
    elif template in ('uztea_brand', 'uztea_simple'):
        inline_images.append(('uztea-logo', 'uztea-logo-white.png', get_uztea_email_logo_bytes()))

    connection, from_email = _email_connection(sender)
    connection.open()  # raises when the SMTP server can't be reached
    try:
        for person in people:
            personal_subject = personalise(subject, person)
            personal_body = personalise(body, person)
            if not person['email']:
                _log(batch, MessageLog.CHANNEL_EMAIL, source, person, user, MessageLog.SKIPPED,
                     subject=personal_subject, body=personal_body, error='No email address')
                continue
            if person.get('unsubscribed'):
                _log(batch, MessageLog.CHANNEL_EMAIL, source, person, user, MessageLog.SKIPPED,
                     subject=personal_subject, body=personal_body, error='Unsubscribed from UzTEA emails')
                continue
            try:
                content = MembershipAdmin._absolute_email_urls(body_to_html(personal_body, is_html))
                html_body = MembershipAdmin._wrap_custom_email(content, template, recipient_name=person['name'])
                message = EmailMultiAlternatives(subject=personal_subject, body=strip_tags(html_body),
                                                 from_email=from_email, to=[person['email']], connection=connection)
                if inline_images:
                    message.mixed_subtype = 'related'
                    for content_id, filename, data in inline_images:
                        image = MIMEImage(data, _subtype='png')
                        image.add_header('Content-ID', f'<{content_id}>')
                        image.add_header('Content-Disposition', 'inline', filename=filename)
                        message.attach(image)
                message.attach_alternative(html_body, 'text/html')
                for filename, data, content_type in attachments:
                    message.attach(filename, data, content_type)
                message.send(fail_silently=False)
                _log(batch, MessageLog.CHANNEL_EMAIL, source, person, user, MessageLog.SENT,
                     subject=personal_subject, body=personal_body)
            except Exception as exc:
                logger.warning('Email to %s #%s failed: %s', source, person['id'], exc)
                _log(batch, MessageLog.CHANNEL_EMAIL, source, person, user, MessageLog.FAILED,
                     subject=personal_subject, body=personal_body, error=str(exc))
    finally:
        connection.close()
    return batch
