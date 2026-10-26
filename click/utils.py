import base64
import hashlib
import os
import json
import logging
import time
import threading
from datetime import timedelta
from urllib import request, error
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('click')


def _fetch_as_data_url(url, fallback_url=None):
    """Fetch a remote image and return it as a base64 data URL."""
    try:
        req = request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with request.urlopen(req, timeout=5) as resp:
            content_type = resp.headers.get_content_type() or 'image/png'
            data = base64.b64encode(resp.read()).decode('utf-8')
            return f'data:{content_type};base64,{data}'
    except Exception as e:
        logger.warning(f"Could not fetch image {url}: {e}")
        return fallback_url or url


def _img_data_url(filename):
    """Read an image from static/images/ and return as base64 data URL."""
    for folder in ['static', 'staticfiles']:
        path = settings.BASE_DIR / folder / 'images' / filename
        try:
            with open(path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
                return f'data:image/png;base64,{data}'
        except Exception:
            continue
    logger.warning(f"Could not read image: {filename}")
    return None


def _logo_data_url():
    return _img_data_url('logo.png')


def _format_phone(phone):
    import re
    digits = re.sub(r'\D', '', str(phone))
    if digits.startswith('998') and len(digits) == 12:
        return f'+{digits[:3]} {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:]}'
    return phone


def build_membership_card_context(membership, order, member_url, demo=False, card_id_override=None):
    institution_name = membership.institution_name or membership.full_name
    initials = ''.join(word[0] for word in institution_name.split()[:3] if word).upper() or 'UZ'
    valid_until = (getattr(order, 'updated_at', None) or timezone.now()) + timedelta(days=365)
    membership_id = getattr(membership, 'id', None)
    if card_id_override:
        card_id = card_id_override
    else:
        card_id = 'UZDEMO' if demo or not membership_id else f'UZ{membership_id:06d}'
    qr_params = urlencode({
        'size': '160x160',
        'data': member_url,
    })
    qr_url = f'https://api.qrserver.com/v1/create-qr-code/?{qr_params}'

    return {
        'order': order,
        'membership': membership,
        'card_id': card_id,
        'card_initials': initials,
        'card_contact_name': membership.contact_person_name or membership.full_name,
        'card_contact_email': membership.contact_person_email or membership.email,
        'card_valid_until': valid_until,
        'card_member_url': member_url,
        'card_qr_url': _fetch_as_data_url(qr_url, fallback_url=qr_url),
        'card_logo_url': _logo_data_url(),
        'card_phone': _format_phone(membership.phone_number),
        'card_topshape_url': _img_data_url('topshape.png'),
        'card_bottomshape_url': _img_data_url('bottomshape.png'),
        'card_siluet_url': _img_data_url('samarqandsiluet.png'),
        'card_righticontop_url': _img_data_url('righticontop.png'),
        'card_tickicon_url': _img_data_url('tickicon.png'),
        'site_url': 'www.uztea.uz',
        'is_demo_card': demo,
    }

def verify_click_signature(params):
    """
    Robust Click signature verification.

    - Converts incoming values to strings.
    - Trims CLICK_SECRET_KEY from environment (also strips surrounding quotes).
    - Builds sign_source exactly per Click docs:
        Prepare (action == "0"):
            click_trans_id + service_id + secret + merchant_trans_id + amount + action + sign_time
        Complete (action == "1"):
            click_trans_id + service_id + secret + merchant_trans_id + merchant_prepare_id + amount + action + sign_time
    - Compares lowercase md5 hex digests.
    - Logs masked secret, masked sign_source, expected and incoming signatures for debugging.
    """

    def _to_str(dct, key):
        v = dct.get(key)
        if v is None:
            return ''
        if isinstance(v, (list, tuple)):
            v = v[0] if v else ''
        return str(v)

    service_id = _to_str(params, 'service_id')
    click_trans_id = _to_str(params, 'click_trans_id')
    merchant_trans_id = _to_str(params, 'merchant_trans_id')
    amount = _to_str(params, 'amount')
    action = _to_str(params, 'action')
    sign_time = _to_str(params, 'sign_time')
    merchant_prepare_id = _to_str(params, 'merchant_prepare_id')

    raw_secret = os.getenv('CLICK_SECRET_KEY') or ''
    secret_key = raw_secret.strip().strip('"').strip("'")

    if not secret_key:
        logger.warning("[SIGN_VERIFY] CLICK_SECRET_KEY is not configured or empty.")
        return False

    if action == '0':
        sign_source = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount}{action}{sign_time}"
    else:
        sign_source = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{merchant_prepare_id}{amount}{action}{sign_time}"

    expected_sign = hashlib.md5(sign_source.encode('utf-8')).hexdigest().lower()

    incoming_sign = ''
    if params.get('sign_string'):
        incoming_sign = str(params.get('sign_string')).strip().lower()
    elif params.get('sign'):
        incoming_sign = str(params.get('sign')).strip().lower()

    masked_secret = (secret_key[:2] + '***' + secret_key[-2:]) if len(secret_key) > 4 else '***'
    sign_source_masked = sign_source.replace(secret_key, masked_secret)

    logger.info(
        "[SIGN_VERIFY] click_trans_id=%s service_id=%s action=%s sign_time=%s amount=%s secret_mask=%s "
        "expected_sign=%s incoming_sign=%s sign_source_masked=%s",
        click_trans_id, service_id, action, sign_time, amount, masked_secret,
        expected_sign, incoming_sign, sign_source_masked
    )

    return expected_sign == incoming_sign

def get_card_payment_url(order_id, amount):
    """
    Click "Pay with any card" button — Click foydalanuvchisi bo'lmagan
    odamlar ham istalgan karta bilan to'lay oladi.
    https://docs.click.uz/click-pay-by-card/
    """
    service_id = os.getenv('CLICK_SERVICE_ID')
    merchant_id = os.getenv('CLICK_MERCHANT_ID')
    base_url = os.getenv('SITE_BASE_URL', 'http://127.0.0.1:8000')
    return_url = f"{base_url}/payments/click/status/{order_id}/"

    url = (
        f"https://my.click.uz/services/pay_with_card?"
        f"service_id={service_id}&"
        f"merchant_id={merchant_id}&"
        f"amount={amount}&"
        f"transaction_param={order_id}&"
        f"return_url={return_url}"
    )
    return url


def get_click_url(order_id, amount):
    service_id = os.getenv('CLICK_SERVICE_ID')
    merchant_id = os.getenv('CLICK_MERCHANT_ID')
    base_url = os.getenv('SITE_BASE_URL', 'http://127.0.0.1:8000')
    return_url = f"{base_url}/payments/click/status/{order_id}/"

    url = (
        f"https://my.click.uz/services/pay?"
        f"service_id={service_id}&"
        f"merchant_id={merchant_id}&"
        f"amount={amount}&"
        f"transaction_param={order_id}&"
        f"return_url={return_url}"
    )
    return url

def submit_fiscal_data(order):
    """
    Submits fiscal data (OFD) to Click API.
    Required by law for all payments.
    Docs: https://docs.click.uz/fiscalization/

    Auth header format : Auth: service_id:sha1(timestamp+api_key):timestamp
    Price/Amount fields: in TIYIN (1 sum = 100 tiyin)
    """
    service_id = os.getenv('CLICK_SERVICE_ID')
    api_key = os.getenv('CLICK_API_KEY')
    tin = os.getenv('CLICK_TIN', '')  # Tashkilot STIR (INN)

    if not api_key or api_key == 'YOUR_MERCHANT_API_KEY':
        logger.warning(f"Skipping fiscalization for Order #{order.id}: CLICK_API_KEY not configured.")
        return False

    if not tin or tin == 'YOUR_TIN_OR_STIR':
        logger.warning(f"Skipping fiscalization for Order #{order.id}: CLICK_TIN not configured.")
        return False

    # IKPU va Package kodlarni Click yoki soliq idorasidan oling
    IKPU_CODE = os.getenv('CLICK_IKPU_CODE', '10101001001000000')
    PACKAGE_CODE = os.getenv('CLICK_PACKAGE_CODE', '123456')

    # Barcha pul miqdorlari TIYINda bo'lishi shart (1 sum = 100 tiyin)
    amount_tiyin = int(float(order.amount) * 100)

    items = [
        {
            "Name": f"A'zolik to'lovi: {order.membership.get_membership_type_display()}",
            "SPIC": IKPU_CODE,           # 17 belgili IKPU kodi
            "PackageCode": PACKAGE_CODE,  # 20 belgigacha
            "Price": amount_tiyin,        # Jami narx — TIYINda
            "Amount": 1,                  # Miqdor (dona)
            "VAT": 0,                     # QQS summasi — TIYINda (0 = soliqdan ozod)
            "VATPercent": 0,              # QQS foizi
            "CommissionInfo": {
                "TIN": tin,               # Tashkilot STIR
            },
        }
    ]

    timestamp = int(time.time())
    # Auth: service_id:sha1(timestamp+api_key):timestamp
    auth_hash = hashlib.sha1(f"{timestamp}{api_key}".encode('utf-8')).hexdigest()
    auth_header = f"{service_id}:{auth_hash}:{timestamp}"

    data = {
        "service_id": int(service_id),
        "payment_id": int(order.click_paydoc_id or order.click_trans_id or 0),
        "items": items,
        "received_ecash": 0,
        "received_cash": 0,
        "received_card": amount_tiyin,   # TIYINda
    }

    url = "https://api.click.uz/v2/merchant/payment/ofd_data/submit_items"

    req = request.Request(url, data=json.dumps(data).encode('utf-8'), method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json')
    req.add_header('Auth', auth_header)

    try:
        with request.urlopen(req, timeout=10) as response:
            res_data = json.load(response)
            if res_data.get('error_code') not in (None, 0):
                logger.error(f"Fiscalization failed for Order #{order.id}: {res_data}")
                return False
            logger.info(f"Fiscalization success for Order #{order.id}: {res_data}")
            return True
    except error.URLError as e:
        logger.error(f"Fiscalization failed for Order #{order.id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Fiscalization error for Order #{order.id}: {str(e)}")
        return False


def submit_fiscal_data_async(order_id):
    """
    Run fiscalization outside the Click webhook response path.

    Click expects a quick Complete response; blocking on OFD can leave the
    customer-facing Click page in a pending state even after we mark the order
    as paid locally.
    """
    def _runner():
        from django.db import close_old_connections

        close_old_connections()
        try:
            from .models import Order

            order = Order.objects.select_related('membership').get(pk=order_id)
            submit_fiscal_data(order)
        except Exception as exc:
            logger.exception(f"Fiscalization background task failed for Order #{order_id}: {exc}")
        finally:
            close_old_connections()

    thread = threading.Thread(target=_runner, name=f'click-ofd-{order_id}', daemon=True)
    thread.start()
