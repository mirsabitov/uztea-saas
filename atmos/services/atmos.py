import logging
import base64

import requests
from django.conf import settings

logger = logging.getLogger('atmos')

REQUEST_TIMEOUT = 30


class AtmosError(Exception):
    def __init__(self, message: str, code: str = 'ATMOS_ERROR', raw: dict = None):
        super().__init__(message)
        self.code = code
        self.raw = raw or {}


class AtmosService:
    def __init__(self):
        self.base_url       = str(settings.ATMOS_BASE_URL).strip().rstrip('/')
        self.consumer_key   = str(settings.ATMOS_CONSUMER_KEY).strip()
        self.consumer_secret = str(settings.ATMOS_CONSUMER_SECRET).strip()
        self.store_id       = str(settings.ATMOS_STORE_ID).strip()
        self.terminal_id    = str(getattr(settings, 'ATMOS_TERMINAL_ID', '')).strip()
        self._token: str | None = None
        try:
            self._store_id_int = int(self.store_id)
        except (ValueError, TypeError):
            self._store_id_int = 0

    # ── helpers ──────────────────────────────────────────────────────── #

    def _basic_auth_header(self) -> str:
        creds = f'{self.consumer_key}:{self.consumer_secret}'
        return 'Basic ' + base64.b64encode(creds.encode()).decode()

    @staticmethod
    def _mask_token(token: str) -> str:
        return f'{token[:8]}...{token[-6:]}' if len(token) > 14 else token[:4] + '...'

    def _get_token(self) -> str:
        if self._token:
            return self._token

        if not self.consumer_key or not self.consumer_secret:
            raise AtmosError('Atmos credentials are not configured.', code='AUTH_CONFIG_ERROR')

        url = f'{self.base_url}/token'
        logger.info('ATMOS | token request | url=%s store_id=%s', url, self.store_id)
        try:
            resp = requests.post(
                url,
                headers={
                    'Authorization': self._basic_auth_header(),
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data='grant_type=client_credentials',
                timeout=REQUEST_TIMEOUT,
            )
        except requests.Timeout:
            raise AtmosError('Token request timed out.', code='TIMEOUT')
        except requests.RequestException as exc:
            raise AtmosError(f'Token request failed: {exc}', code='NETWORK_ERROR')

        try:
            data = self._parse_response(resp, step='get_token')
        except AtmosError as exc:
            if resp.status_code in (401, 403):
                raise AtmosError(
                    'Atmos token authentication failed. Check consumer key, consumer secret, and environment.',
                    code='AUTH_ERROR',
                    raw=exc.raw,
                )
            raise

        token = data.get('access_token')
        if not token:
            raise AtmosError('No access_token in response.', code='TOKEN_MISSING', raw=data)

        self._token = token
        logger.info('ATMOS | token acquired | token=%s', self._mask_token(token))
        return self._token

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self._get_token()}',
            'Content-Type': 'application/json',
        }

    def _post(self, path: str, payload: dict, step: str) -> dict:
        url = f'{self.base_url}{path}'
        logger.debug('ATMOS | [%s] POST %s | %s', step, url, payload)
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=REQUEST_TIMEOUT)
        except requests.Timeout:
            raise AtmosError(f'[{step}] Request timed out.', code='TIMEOUT')
        except requests.RequestException as exc:
            raise AtmosError(f'[{step}] Network error: {exc}', code='NETWORK_ERROR')
        return self._parse_response(resp, step=step)

    @staticmethod
    def _parse_response(resp: requests.Response, step: str) -> dict:
        try:
            data = resp.json()
        except ValueError:
            raise AtmosError(
                f'[{step}] Non-JSON response (HTTP {resp.status_code}).',
                code='INVALID_RESPONSE',
            )

        logger.debug('ATMOS | [%s] status=%s body=%s', step, resp.status_code, data)

        if not resp.ok:
            msg = (data.get('message') or data.get('error_description')
                   or data.get('error') or f'HTTP {resp.status_code}')
            raise AtmosError(f'[{step}] {msg}', code='API_ERROR', raw=data)

        result = data.get('result', {})
        code = str(result.get('code', '0'))
        if code not in ('0', '200', '', 'OK'):
            raise AtmosError(
                f'[{step}] {result.get("description", "Unknown error")}',
                code=f'RESULT_{code}',
                raw=data,
            )
        return data

    # ── public methods ────────────────────────────────────────────────── #

    def create_payment(self, amount: int, account: str) -> dict:
        payload = {'amount': amount, 'account': account, 'store_id': self._store_id_int, 'lang': 'ru'}
        if self.terminal_id:
            payload['terminal_id'] = self.terminal_id

        logger.info('ATMOS | create | account=%s amount=%s', account, amount)
        data = self._post('/merchant/pay/create', payload, step='create_payment')

        transaction_id = data.get('transaction_id')
        if not transaction_id:
            raise AtmosError('No transaction_id in create response.', code='INVALID_RESPONSE', raw=data)

        store_txn = data.get('store_transaction') or {}
        logger.info('ATMOS | create | transaction_id=%s', transaction_id)
        return {
            'transaction_id':       str(transaction_id),
            'atmos_transaction_id': str(store_txn.get('trans_id', '')),
            'store_id':             str(self.store_id),
            'raw':                  data,
        }

    def pre_apply(self, transaction_id: str, card_number: str, expiry: str) -> dict:
        payload = {
            'transaction_id': transaction_id,
            'card_number':    card_number,
            'expiry':         expiry,
            'store_id':       self._store_id_int,
            'lang':           'ru',
        }
        logger.info('ATMOS | pre_apply | transaction_id=%s card_tail=%s', transaction_id, card_number[-4:])
        data = self._post('/merchant/pay/pre-apply', payload, step='pre_apply')
        logger.info('ATMOS | pre_apply | OTP sent | transaction_id=%s', transaction_id)
        return {'raw': data}

    def apply(self, transaction_id: str, otp: str) -> dict:
        payload = {'transaction_id': transaction_id, 'otp': otp, 'store_id': self._store_id_int, 'lang': 'ru'}
        logger.info('ATMOS | apply | transaction_id=%s', transaction_id)
        data = self._post('/merchant/pay/apply', payload, step='apply')
        logger.info('ATMOS | apply | confirmed | transaction_id=%s', transaction_id)
        return {'raw': data, 'success': True}

    def retry_otp(self, transaction_id: str) -> dict:
        payload = {'transaction_id': transaction_id, 'store_id': self._store_id_int}
        logger.info('ATMOS | retry_otp | transaction_id=%s', transaction_id)
        data = self._post('/merchant/pay/retry-otp', payload, step='retry_otp')
        logger.info('ATMOS | retry_otp | OTP resent | transaction_id=%s', transaction_id)
        return {'raw': data}

    def reverse_payment(self, transaction_id: str, reason: str) -> dict:
        atmos_transaction_id = int(transaction_id) if str(transaction_id).isdigit() else transaction_id
        payload = {
            'transaction_id': atmos_transaction_id,
            'reason': reason,
        }
        logger.info('ATMOS | reverse_payment | transaction_id=%s', transaction_id)
        data = self._post('/merchant/pay/reverse', payload, step='reverse_payment')
        logger.info('ATMOS | reverse_payment | cancelled | transaction_id=%s', transaction_id)
        return {'raw': data, 'transaction_id': str(data.get('transaction_id', transaction_id)), 'success': True}

    # ── MPS (Visa / Mastercard) ───────────────────────────────────────── #

    def mps_bind_card(self, pan: str, expiry: str, cvc2: str, card_name: str,
                      client_ip: str, ext_id: str) -> dict:
        payload = {
            'store_id':       self._store_id_int,
            'pan':            pan,
            'expiry':         expiry,
            'card_name':      card_name,
            'cvc2':           cvc2,
            'client_ip_addr': client_ip,
            'ext_id':         ext_id,
            'lang':           'ru',
        }
        logger.info('ATMOS | mps_bind_card | pan_tail=%s ext_id=%s', pan[-4:], ext_id)
        data = self._post('/mps/pay/card/bind', payload, step='mps_bind_card')
        payload_data = data.get('data') or data
        card_id      = payload_data.get('card_id') or payload_data.get('id')
        redirect_uri = payload_data.get('redirect_uri') or payload_data.get('redirectUri')
        logger.info('ATMOS | mps_bind_card | card_id=%s redirect=%s', card_id, bool(redirect_uri))
        return {'card_id': str(card_id) if card_id else None, 'redirect_uri': redirect_uri, 'raw': data}

    def mps_pre_create(self, amount: int, ext_id: str, account: str,
                       invoice_id: str, ofd_items: list) -> dict:
        payload = {
            'store_id':   self._store_id_int,
            'amount':     amount,
            'ext_id':     ext_id,
            'account':    account,
            'invoice_id': invoice_id,
            'ofd_items':  ofd_items,
            'lang':       'ru',
        }
        logger.info('ATMOS | mps_pre_create | account=%s amount=%s', account, amount)
        data = self._post('/mps/pay/transaction/pre-create', payload, step='mps_pre_create')
        payload_data   = data.get('data') or data
        transaction_id = payload_data.get('transaction_id') or payload_data.get('id')
        if not transaction_id:
            raise AtmosError('No transaction_id in mps_pre_create response.', code='INVALID_RESPONSE', raw=data)
        logger.info('ATMOS | mps_pre_create | transaction_id=%s', transaction_id)
        return {'transaction_id': str(transaction_id), 'raw': data}

    def mps_create_bind(self, card_id: str, amount: int,
                        client_ip: str, transaction_id: str) -> dict:
        payload = {
            'card_id':        card_id,
            'amount':         amount,
            'client_ip_addr': client_ip,
            'transaction_id': transaction_id,
        }
        logger.info('ATMOS | mps_create_bind | card_id=%s transaction_id=%s', card_id, transaction_id)
        data = self._post('/mps/pay/transaction/create/bind', payload, step='mps_create_bind')
        payload_data = data.get('data') or data
        redirect_uri = payload_data.get('redirect_uri') or payload_data.get('redirectUri')
        logger.info('ATMOS | mps_create_bind | redirect=%s', bool(redirect_uri))
        return {'redirect_uri': redirect_uri, 'raw': data}

    def mps_apply(self, transaction_id: str) -> dict:
        payload = {'transaction_id': transaction_id}
        logger.info('ATMOS | mps_apply | transaction_id=%s', transaction_id)
        data = self._post('/mps/pay/transaction/apply', payload, step='mps_apply')
        logger.info('ATMOS | mps_apply | confirmed | transaction_id=%s', transaction_id)
        return {'raw': data, 'success': True}
