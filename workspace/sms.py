"""Eskiz.uz SMS client (https://notify.eskiz.uz).

Credentials come from .env only: ESKIZ_EMAIL, ESKIZ_PASSWORD, ESKIZ_FROM (sender
name / nickname, "4546" for the default test sender), optional ESKIZ_BASE_URL.
Eskiz only delivers texts that match a template approved in the Eskiz cabinet;
a test account can only send its fixed test text.
"""
import logging
import os
import re
import threading
import time

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://notify.eskiz.uz/api'
TOKEN_TTL = 25 * 24 * 3600  # Eskiz tokens live 30 days; refresh a little earlier.
TIMEOUT = 15

_token_lock = threading.Lock()
_token = {'value': None, 'at': 0.0}


class EskizError(Exception):
    pass


def config():
    return {
        'base_url': (os.getenv('ESKIZ_BASE_URL') or DEFAULT_BASE_URL).rstrip('/'),
        'email': os.getenv('ESKIZ_EMAIL', ''),
        'password': os.getenv('ESKIZ_PASSWORD', ''),
        'sender': os.getenv('ESKIZ_FROM', '4546'),
    }


def is_configured():
    cfg = config()
    return bool(cfg['email'] and cfg['password'])


def normalize_phone(raw):
    """'+998 (90) 123-45-67' / '901234567' -> '998901234567'; None when it isn't an Uzbek mobile number."""
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 9:
        digits = '998' + digits
    if len(digits) == 12 and digits.startswith('998'):
        return digits
    return None


def sms_parts(text):
    """How many SMS a text costs: 160/153 latin, 70/67 when it has non-GSM (e.g. Cyrillic) characters."""
    text = text or ''
    unicode_text = any(ord(ch) > 127 for ch in text)
    single, multi = (70, 67) if unicode_text else (160, 153)
    if len(text) <= single:
        return 1 if text else 0
    return -(-len(text) // multi)


def _login(cfg):
    response = requests.post(f"{cfg['base_url']}/auth/login",
                             data={'email': cfg['email'], 'password': cfg['password']}, timeout=TIMEOUT)
    if response.status_code != 200:
        raise EskizError(f'Eskiz login failed (HTTP {response.status_code}).')
    token = (response.json().get('data') or {}).get('token')
    if not token:
        raise EskizError('Eskiz login returned no token.')
    _token.update(value=token, at=time.time())
    return token


def _get_token(cfg, force=False):
    with _token_lock:
        if force or not _token['value'] or time.time() - _token['at'] > TOKEN_TTL:
            return _login(cfg)
        return _token['value']


def send_sms(phone, text, callback_url=None):
    """Send one SMS. Returns Eskiz's message id; raises EskizError on failure."""
    if not is_configured():
        raise EskizError('Eskiz is not configured.')
    cfg = config()
    data = {'mobile_phone': phone, 'message': text, 'from': cfg['sender']}
    if callback_url:
        data['callback_url'] = callback_url
    for attempt in (1, 2):
        token = _get_token(cfg, force=attempt == 2)
        response = requests.post(f"{cfg['base_url']}/message/sms/send", data=data,
                                 headers={'Authorization': f'Bearer {token}'}, timeout=TIMEOUT)
        if response.status_code == 401 and attempt == 1:
            continue  # token expired — log in again once
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code == 200 and payload.get('id'):
            return str(payload['id'])
        message = payload.get('message') or payload.get('status') or f'HTTP {response.status_code}'
        raise EskizError(f'Eskiz rejected the SMS: {message}')
    raise EskizError('Eskiz authorisation failed.')
