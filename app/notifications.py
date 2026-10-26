import logging
import threading

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _escape_html(value):
    return (
        str(value or '')
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def _format_payment_time(order):
    paid_at = getattr(order, 'updated_at', None) or timezone.now()
    return timezone.localtime(paid_at).strftime('%d.%m.%Y %H:%M')


def build_membership_purchase_message(order, source='Payment'):
    membership = order.membership
    membership_id = f'UZ{membership.id:06d}'

    lines = [
        '<b>New membership purchase</b>',
        f'<b>ID:</b> {_escape_html(membership_id)}',
        f'<b>Full name:</b> {_escape_html(membership.full_name)}',
        f'<b>Email:</b> {_escape_html(membership.email)}',
        f'<b>Membership:</b> {_escape_html(membership.get_membership_type_display())}',
        f'<b>Position:</b> {_escape_html(membership.get_position_display())}',
        f'<b>Amount:</b> {_escape_html(f"{order.amount:,.0f} UZS")}',
        f'<b>Paid at:</b> {_escape_html(_format_payment_time(order))}',
        f'<b>Source:</b> {_escape_html(source)}',
    ]
    return '\n'.join(lines)


def send_membership_purchase_notification(order_id, source='Payment'):
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    chat_id = getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', '')

    if not token or not chat_id:
        logger.info('Telegram notification skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_CHAT_ID is not configured.')
        return False

    try:
        from click.models import Order

        order = Order.objects.select_related('membership').get(pk=order_id)
        message = build_membership_purchase_message(order, source=source)
        response = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            },
            timeout=10,
        )
        response.raise_for_status()
        logger.info('Telegram notification sent for order #%s', order_id)
        return True
    except Exception as exc:
        logger.exception('Telegram notification failed for order #%s: %s', order_id, exc)
        return False


def send_membership_purchase_notification_async(order_id, source='Payment'):
    def _runner():
        from django.db import close_old_connections

        close_old_connections()
        try:
            send_membership_purchase_notification(order_id, source=source)
        finally:
            close_old_connections()

    thread = threading.Thread(
        target=_runner,
        name=f'membership-notify-{order_id}',
        daemon=True,
    )
    thread.start()


def send_membership_welcome_email(order_id):
    from datetime import timedelta

    from click.models import Order
    from atmos.email import send_welcome_email

    order = Order.objects.select_related('membership').get(pk=order_id)
    membership = order.membership
    if not membership.email:
        logger.info('Welcome email skipped for order #%s: membership has no email.', order_id)
        return
    send_welcome_email(
        email=membership.email,
        full_name=membership.full_name,
        membership_id=f'UZ{membership.id:06d}',
        membership_type=membership.get_membership_type_display(),
        expiry_date=(timezone.now() + timedelta(days=365)).strftime('%d %B %Y'),
    )


def send_membership_welcome_email_async(order_id):
    def _runner():
        from django.db import close_old_connections

        close_old_connections()
        try:
            send_membership_welcome_email(order_id)
        except Exception as exc:
            logger.exception('Welcome email failed for order #%s: %s', order_id, exc)
        finally:
            close_old_connections()

    thread = threading.Thread(
        target=_runner,
        name=f'membership-welcome-{order_id}',
        daemon=True,
    )
    thread.start()
