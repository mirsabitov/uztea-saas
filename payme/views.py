import base64
import json
import logging
import hmac
from decimal import Decimal
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from click.models import Order
from .models import PaymeTransaction, PaymeConfig

logger = logging.getLogger('payme')


def generate_payme_url(order):
    merchant_id   = settings.PAYME_CASHBOX_ID
    amount        = int(order.amount * 100)
    membership_id = order.payme_account_id
    base_url      = settings.SITE_BASE_URL.rstrip('/')
    return_url    = f"{base_url}/payments/click/status/{order.id}/"
    if order.conference_registration_id:
        return_url = base_url + reverse('conference_payment', args=[order.conference_registration.payment_token])
    params        = (
        f"m={merchant_id}"
        f";ac.order_id={order.id}"
        f";ac.user_id={membership_id}"
        f";a={amount}"
        f";c={return_url}"
        f";ct=1500"
    )
    params_b64 = base64.b64encode(params.encode()).decode()
    return f"{settings.PAYME_URL}/{params_b64}"


@method_decorator(csrf_exempt, name='dispatch')
class PaymeMerchantAPIView(View):

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return self._error(None, -32700, "Parse error", "error.parse_error")

        if not self._check_auth(request):
            return self._error(data.get('id'), -32504, "Authorization failed", "error.authorization")

        method     = data.get('method')
        params     = data.get('params', {})
        request_id = data.get('id')

        handlers = {
            'CheckPerformTransaction': self._check_perform,
            'CreateTransaction':       self._create,
            'PerformTransaction':      self._perform,
            'CancelTransaction':       self._cancel,
            'CheckTransaction':        self._check,
            'GetStatement':            self._statement,
            'ChangePassword':          self._change_password,
        }
        handler = handlers.get(method)
        if handler is None:
            return self._error(request_id, -32601, "Method not found", "error.method_not_found")

        try:
            return handler(params, request_id)
        except Exception as e:
            logger.error(f"Payme {method} error: {e}", exc_info=True)
            return self._error(request_id, -32400, "Internal server error", "error.internal")

    # ── Auth ──────────────────────────────────────────────────────────
    def _check_auth(self, request):
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.startswith('Basic '):
            return False
        try:
            username, password = base64.b64decode(auth[6:]).decode().split(':', 1)
            secret = PaymeConfig.get_secret_key()
            return username == 'Paycom' and bool(secret) and hmac.compare_digest(password, secret)
        except Exception:
            return False

    # ── CheckPerformTransaction ───────────────────────────────────────
    def _check_perform(self, params, rid):
        account       = params.get('account', {})
        order_id      = account.get('order_id')
        user_id       = account.get('user_id')
        amount        = params.get('amount')

        try:
            order = Order.objects.select_related('membership').get(id=order_id)
        except Order.DoesNotExist:
            return self._error(rid, -31050, "Order not found", "error.order_not_found")

        # membership_id ni user_id bilan solishtirish
        if str(order.payme_account_id) != str(user_id):
            return self._error(rid, -31050, "User not found", "error.user_not_found")

        if order.status == 'paid':
            return self._error(rid, -31051, "Order already paid", "error.order_already_paid")

        if amount != int(order.amount * 100):
            return self._error(rid, -31001, "Incorrect amount", "error.incorrect_amount")

        return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {'allow': True}})

    # ── CreateTransaction ─────────────────────────────────────────────
    def _create(self, params, rid):
        account        = params.get('account', {})
        transaction_id = params.get('id')
        amount         = params.get('amount')
        order_id       = account.get('order_id')
        user_id        = account.get('user_id')

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return self._error(rid, -31050, "Order not found", "error.order_not_found")

        if str(order.payme_account_id) != str(user_id):
            return self._error(rid, -31050, "User not found", "error.user_not_found")

        if order.status == 'paid':
            return self._error(rid, -31051, "Order already paid", "error.order_already_paid")

        if amount != int(order.amount * 100):
            return self._error(rid, -31001, "Incorrect amount", "error.incorrect_amount")

        existing = PaymeTransaction.objects.filter(transaction_id=transaction_id).first()
        if existing:
            if existing.order_id != order.id:
                return self._error(rid, -31050, "Transaction belongs to another order", "error.order_not_found")
            if existing.state == 1:
                return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {
                    'create_time': int(existing.created_at.timestamp() * 1000),
                    'transaction': str(existing.id),
                    'state': existing.state,
                }})
            elif existing.state == 2:
                return self._error(rid, -31051, "Already paid", "error.already_paid")
            else:
                return self._error(rid, -31008, "Transaction cancelled", "error.transaction_cancelled")

        if PaymeTransaction.objects.filter(order=order, state=1).exists():
            return self._error(rid, -31099, "Pending transaction exists", "error.pending_transaction_exists")

        txn = PaymeTransaction.objects.create(
            transaction_id=transaction_id,
            order=order,
            amount=Decimal(amount) / 100,
            state=1,
        )
        order.status = 'processing'
        order.save(update_fields=['status'])

        return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {
            'create_time': int(txn.created_at.timestamp() * 1000),
            'transaction': str(txn.id),
            'state': txn.state,
        }})

    # ── PerformTransaction ────────────────────────────────────────────
    def _perform(self, params, rid):
        try:
            txn = PaymeTransaction.objects.get(transaction_id=params.get('id'))
        except PaymeTransaction.DoesNotExist:
            return self._error(rid, -31003, "Transaction not found", "error.transaction_not_found")

        if txn.state == 2:
            return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {
                'transaction': str(txn.id),
                'perform_time': int(txn.performed_at.timestamp() * 1000),
                'state': txn.state,
            }})

        if txn.state != 1:
            return self._error(rid, -31008, "Cannot perform cancelled transaction", "error.cannot_perform")

        txn.state        = 2
        txn.performed_at = timezone.now()
        txn.save()

        order         = txn.order
        order.status  = 'paid'
        order.save(update_fields=['status', 'updated_at'])

        from app.notifications import (
            send_membership_purchase_notification_async,
            send_membership_welcome_email_async,
        )
        if order.membership_id:
            send_membership_purchase_notification_async(order.id, source='Payme')
            send_membership_welcome_email_async(order.id)

        logger.info(f"Order #{order.id} paid via Payme. Membership: {order.membership_id}")

        return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {
            'transaction': str(txn.id),
            'perform_time': int(txn.performed_at.timestamp() * 1000),
            'state': txn.state,
        }})

    # ── CancelTransaction ─────────────────────────────────────────────
    def _cancel(self, params, rid):
        try:
            txn = PaymeTransaction.objects.get(transaction_id=params.get('id'))
        except PaymeTransaction.DoesNotExist:
            return self._error(rid, -31003, "Transaction not found", "error.transaction_not_found")

        reason = params.get('reason')

        if txn.state == 1:
            txn.state        = -1
            txn.reason       = reason
            txn.cancelled_at = timezone.now()
            txn.save()
            txn.order.status = 'failed'
            txn.order.save(update_fields=['status'])

        elif txn.state == 2:
            txn.state        = -2
            txn.reason       = reason
            txn.cancelled_at = timezone.now()
            txn.save()
            txn.order.status = 'failed'
            txn.order.save(update_fields=['status'])

        return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {
            'transaction': str(txn.id),
            'cancel_time': int(txn.cancelled_at.timestamp() * 1000),
            'state': txn.state,
        }})

    # ── CheckTransaction ──────────────────────────────────────────────
    def _check(self, params, rid):
        try:
            txn = PaymeTransaction.objects.get(transaction_id=params.get('id'))
        except PaymeTransaction.DoesNotExist:
            return self._error(rid, -31003, "Transaction not found", "error.transaction_not_found")

        return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {
            'create_time':  int(txn.created_at.timestamp() * 1000),
            'perform_time': int(txn.performed_at.timestamp() * 1000) if txn.performed_at else 0,
            'cancel_time':  int(txn.cancelled_at.timestamp() * 1000) if txn.cancelled_at else 0,
            'transaction':  str(txn.id),
            'state':        txn.state,
            'reason':       txn.reason,
        }})

    # ── GetStatement ──────────────────────────────────────────────────
    def _statement(self, params, rid):
        from_dt = datetime.fromtimestamp(params.get('from') / 1000)
        to_dt   = datetime.fromtimestamp(params.get('to') / 1000)

        txns = PaymeTransaction.objects.filter(created_at__gte=from_dt, created_at__lte=to_dt)
        result = [{
            'id':           txn.transaction_id,
            'time':         int(txn.created_at.timestamp() * 1000),
            'amount':       int(txn.amount * 100),
            'account':      {'order_id': txn.order_id},
            'create_time':  int(txn.created_at.timestamp() * 1000),
            'perform_time': int(txn.performed_at.timestamp() * 1000) if txn.performed_at else 0,
            'cancel_time':  int(txn.cancelled_at.timestamp() * 1000) if txn.cancelled_at else 0,
            'transaction':  str(txn.id),
            'state':        txn.state,
            'reason':       txn.reason,
        } for txn in txns]

        return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {'transactions': result}})

    # ── ChangePassword ────────────────────────────────────────────────
    def _change_password(self, params, rid):
        new_password = params.get('password')
        if not new_password:
            return self._error(rid, -32600, "Password required", "error.password_required")
        PaymeConfig.set_secret_key(new_password)
        logger.info("Payme secret key updated via ChangePassword")
        return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'result': {'success': True}})

    # ── Helper ────────────────────────────────────────────────────────
    def _error(self, rid, code, message, data):
        return JsonResponse({'jsonrpc': '2.0', 'id': rid, 'error': {
            'code': code, 'message': message, 'data': data,
        }})
