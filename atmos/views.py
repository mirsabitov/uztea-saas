import logging
import uuid

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.shortcuts import render

import uuid as _uuid
from .models import AtmosTransaction, PaymentStatus, PaymentType
from .email import send_fiscal_receipt, send_welcome_email, send_member_card_email


def _notify_success(order, txn, ofd_url):
    """Send welcome email + fiscal receipt to the member after successful payment.

    For Institutional memberships, also email each team member their own
    membership-card link.
    """
    import os
    from datetime import timedelta
    from django.urls import reverse
    from django.utils import timezone

    membership = order.membership
    from app.notifications import send_membership_purchase_notification_async
    send_membership_purchase_notification_async(order.id, source=f'Atmos {txn.payment_type}')

    membership_id = f'UZ{membership.id:06d}'
    expiry = (timezone.now() + timedelta(days=365)).strftime('%d %B %Y')
    type_display = membership.get_membership_type_display()

    if membership.email:
        # Welcome email — always on success
        send_welcome_email(
            email=membership.email,
            full_name=membership.full_name,
            membership_id=membership_id,
            membership_type=type_display,
            expiry_date=expiry,
        )

        # Fiscal receipt — only when OFD url is available
        if ofd_url:
            send_fiscal_receipt(
                email=membership.email,
                full_name=membership.full_name,
                amount_uzs=txn.amount_uzs,
                ofd_url=ofd_url,
                order_id=str(txn.account),
                membership_type=type_display,
            )

    # Institutional: send each team member their own card link
    if membership.membership_type == 'institutional':
        base = os.getenv('SITE_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
        for idx in (2, 3, 4, 5):
            name = getattr(membership, f'member_{idx}_name', None)
            mail = getattr(membership, f'member_{idx}_email', None)
            if not name or not mail:
                continue
            card_url = base + reverse('team_member_card', args=[order.pk, idx])
            send_member_card_email(
                email=mail,
                full_name=name,
                card_url=card_url,
                membership_id=f'{membership_id}-{idx - 1}',
                institution_name=membership.institution_name or '',
            )
from .serializers import (
    StartPaymentSerializer,
    ConfirmPaymentSerializer,
    RetryOtpSerializer,
    AtmosTransactionSerializer,
    MpsStartSerializer,
    MpsApplySerializer,
)
from .services.atmos import AtmosService, AtmosError

logger = logging.getLogger('atmos')


def _ok(data: dict) -> Response:
    return Response({'success': True, **data})


def _err(message: str, code: str = 'ERROR', http_status: int = 400) -> Response:
    return Response(
        {'success': False, 'error': {'message': message, 'code': code}},
        status=http_status,
    )


def _first_error(serializer) -> str:
    field, errors = next(iter(serializer.errors.items()))
    return f'{field}: {errors[0]}' if errors else 'Invalid request data.'


# ── Payment page ────────────────────────────────────────────────────── #

def payment_page(request):
    return render(request, 'atmos/payment.html')


# ── API: start ──────────────────────────────────────────────────────── #

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def start_payment(request):
    s = StartPaymentSerializer(data=request.data)
    if not s.is_valid():
        return _err(_first_error(s), code='VALIDATION_ERROR')

    data        = s.validated_data
    card_number = data['card_number']

    txn = AtmosTransaction(
        amount=data['amount'],
        account=data['account'],
        status=PaymentStatus.PENDING,
        raw_request={
            'amount':            data['amount'],
            'account':           data['account'],
            'card_number_tail':  card_number[-4:],
        },
    )

    service = AtmosService()
    try:
        create = service.create_payment(amount=data['amount'], account=data['account'])
        txn.transaction_id       = create['transaction_id']
        txn.atmos_transaction_id = create['atmos_transaction_id']
        txn.store_id             = create['store_id']
        txn.card_number_masked   = AtmosTransaction.mask_card(card_number)
        txn.raw_response         = create['raw']

        pre = service.pre_apply(txn.transaction_id, card_number, data['expiry'])
        txn.status       = PaymentStatus.OTP_SENT
        txn.raw_response = {**txn.raw_response, 'pre_apply': pre['raw']}
        txn.save()

        logger.info('start_payment | OTP sent | transaction_id=%s', txn.transaction_id)
        return _ok({'transaction_id': txn.transaction_id, 'message': 'OTP sent to your phone.'})

    except AtmosError as exc:
        txn.status        = PaymentStatus.FAILED
        txn.error_message = str(exc)
        txn.raw_response  = exc.raw
        if not txn.transaction_id:
            txn.transaction_id = f'failed-{uuid.uuid4()}'
        txn.save()
        logger.error('start_payment | AtmosError: %s', exc)
        return _err(str(exc), code=exc.code, http_status=status.HTTP_502_BAD_GATEWAY)

    except Exception:
        logger.exception('start_payment | unexpected error')
        return _err('An unexpected error occurred.', code='INTERNAL_ERROR', http_status=500)


# ── API: retry OTP ──────────────────────────────────────────────────── #

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def retry_otp(request):
    s = RetryOtpSerializer(data=request.data)
    if not s.is_valid():
        return _err(_first_error(s), code='VALIDATION_ERROR')

    transaction_id = s.validated_data['transaction_id']
    try:
        txn = AtmosTransaction.objects.get(transaction_id=transaction_id)
    except AtmosTransaction.DoesNotExist:
        return _err('Transaction not found.', code='NOT_FOUND', http_status=404)

    if txn.status != PaymentStatus.OTP_SENT:
        return _err(f'Cannot resend OTP — status is {txn.status}.', code='INVALID_STATE')

    service = AtmosService()
    try:
        result = service.retry_otp(txn.transaction_id)
        txn.raw_response = {**txn.raw_response, 'retry_otp': result['raw']}
        txn.save(update_fields=['raw_response', 'updated_at'])
        return _ok({'transaction_id': txn.transaction_id, 'message': 'OTP resent successfully.'})
    except AtmosError as exc:
        logger.error('retry_otp | AtmosError: %s', exc)
        return _err(str(exc), code=exc.code, http_status=status.HTTP_502_BAD_GATEWAY)
    except Exception:
        logger.exception('retry_otp | unexpected error')
        return _err('An unexpected error occurred.', code='INTERNAL_ERROR', http_status=500)


# ── API: confirm ─────────────────────────────────────────────────────── #

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def confirm_payment(request):
    s = ConfirmPaymentSerializer(data=request.data)
    if not s.is_valid():
        return _err(_first_error(s), code='VALIDATION_ERROR')

    data = s.validated_data
    try:
        txn = AtmosTransaction.objects.get(transaction_id=data['transaction_id'])
    except AtmosTransaction.DoesNotExist:
        return _err('Transaction not found.', code='NOT_FOUND', http_status=404)

    # Already paid — return success so the frontend can navigate to the card.
    if txn.status == PaymentStatus.SUCCESS:
        return _ok({
            'transaction_id': txn.transaction_id,
            'amount':         txn.amount,
            'amount_uzs':     txn.amount_uzs,
            'account':        txn.account,
            'message':        'Payment already completed.',
        })

    if txn.status != PaymentStatus.OTP_SENT:
        return _err(f'Cannot confirm — status is {txn.status}.', code='INVALID_STATE')

    service = AtmosService()
    try:
        result = service.apply(txn.transaction_id, data['otp'])
        txn.status       = PaymentStatus.SUCCESS
        txn.raw_response = {**txn.raw_response, 'apply': result['raw']}
        txn.save()

        try:
            from click.models import Order
            order = Order.objects.select_related('membership').get(id=int(txn.account), membership__isnull=False)
            order.status = 'paid'
            order.save(update_fields=['status', 'updated_at'])
            ofd_url = result['raw'].get('ofd_url') or result['raw'].get('ofd_url_commission', '')
            _notify_success(order, txn, ofd_url)
        except Exception:
            pass

        logger.info('confirm_payment | SUCCESS | transaction_id=%s', txn.transaction_id)
        return _ok({
            'transaction_id': txn.transaction_id,
            'amount':         txn.amount,
            'amount_uzs':     txn.amount_uzs,
            'account':        txn.account,
            'message':        'Payment completed successfully.',
        })

    except AtmosError as exc:
        txn.status        = PaymentStatus.FAILED
        txn.error_message = str(exc)
        txn.save()
        logger.error('confirm_payment | AtmosError: %s', exc)
        return _err(str(exc), code=exc.code, http_status=status.HTTP_502_BAD_GATEWAY)

    except Exception:
        logger.exception('confirm_payment | unexpected error')
        return _err('An unexpected error occurred.', code='INTERNAL_ERROR', http_status=500)


# ── API: callback ────────────────────────────────────────────────────── #

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def payment_callback(request):
    payload        = request.data
    transaction_id = payload.get('transaction_id')
    logger.info('callback | received | transaction_id=%s', transaction_id)

    if not transaction_id:
        return Response({'status': 0, 'message': 'transaction_id required'}, status=400)

    try:
        txn = AtmosTransaction.objects.get(transaction_id=transaction_id)
    except AtmosTransaction.DoesNotExist:
        return Response({'status': 0, 'message': 'not found'}, status=404)

    status_map = {
        'SUCCESS':   PaymentStatus.SUCCESS,
        'FAILED':    PaymentStatus.FAILED,
        'CANCELLED': PaymentStatus.CANCELLED,
    }
    cb_status = payload.get('status', '').upper()
    if cb_status in status_map:
        txn.status       = status_map[cb_status]
        txn.raw_response = {**txn.raw_response, 'callback': payload}
        txn.save()

    return Response({'status': 1, 'message': 'ok'})


# ── MPS: start (bind card + pre-create + create/bind) ────────────────── #

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def mps_start(request):
    s = MpsStartSerializer(data=request.data)
    if not s.is_valid():
        return _err(_first_error(s), code='VALIDATION_ERROR')

    data       = s.validated_data
    pan        = data['pan']
    client_ip  = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR', '127.0.0.1')
    )
    ext_id     = str(_uuid.uuid4())
    invoice_id = data.get('invoice_id') or data['account']

    ofd_items = [{
        'name':       f"UzTEA membership fee (order #{data['account']})",
        'price':      data['amount'],
        'quantity':   1,
        'vat_percent': 0,
    }]

    txn = AtmosTransaction(
        amount       = data['amount'],
        account      = data['account'],
        payment_type = PaymentType.MPS,
        status       = PaymentStatus.PENDING,
        raw_request  = {'pan_tail': pan[-4:], 'card_name': data['card_name'], 'ext_id': ext_id},
    )

    service = AtmosService()
    try:
        bind   = service.mps_bind_card(pan, data['expiry'], data['cvc2'], data['card_name'], client_ip, ext_id)
        card_id = bind['card_id']
        txn.mps_card_id        = card_id or ''
        txn.card_number_masked = AtmosTransaction.mask_card(pan)
        txn.raw_response       = {'bind': bind['raw']}

        if bind.get('redirect_uri'):
            txn.transaction_id = f'mps-pending-{ext_id}'
            txn.save()
            return _ok({'requires_3ds': True, 'redirect_uri': bind['redirect_uri'],
                        'transaction_id': txn.transaction_id})

        pre    = service.mps_pre_create(data['amount'], ext_id, data['account'], invoice_id, ofd_items)
        txn.transaction_id = pre['transaction_id']
        txn.raw_response   = {**txn.raw_response, 'pre_create': pre['raw']}

        pay    = service.mps_create_bind(card_id, data['amount'], client_ip, pre['transaction_id'])
        txn.raw_response = {**txn.raw_response, 'create_bind': pay['raw']}

        if pay.get('redirect_uri'):
            txn.status = PaymentStatus.CARD_BOUND
            txn.save()
            return _ok({'requires_3ds': True, 'redirect_uri': pay['redirect_uri'],
                        'transaction_id': txn.transaction_id})

        result = service.mps_apply(pre['transaction_id'])
        txn.status       = PaymentStatus.SUCCESS
        txn.raw_response = {**txn.raw_response, 'apply': result['raw']}
        txn.save()

        try:
            from click.models import Order
            order = Order.objects.select_related('membership').get(id=int(txn.account), membership__isnull=False)
            order.status = 'paid'
            order.save(update_fields=['status', 'updated_at'])
            payload  = result['raw'].get('payload') or {}
            ofd_url  = payload.get('ofd_redirect_uri') or payload.get('ofd_commission_uri', '')
            _notify_success(order, txn, ofd_url)
        except Exception:
            pass

        logger.info('mps_start | SUCCESS | transaction_id=%s', txn.transaction_id)
        return _ok({'transaction_id': txn.transaction_id, 'message': 'Payment completed successfully.'})

    except AtmosError as exc:
        txn.status        = PaymentStatus.FAILED
        txn.error_message = str(exc)
        txn.raw_response  = {**getattr(txn, 'raw_response', {}), 'error': exc.raw}
        if not txn.transaction_id:
            txn.transaction_id = f'mps-failed-{_uuid.uuid4()}'
        txn.save()
        logger.error('mps_start | AtmosError: %s', exc)
        return _err(str(exc), code=exc.code, http_status=status.HTTP_502_BAD_GATEWAY)

    except Exception:
        logger.exception('mps_start | unexpected error')
        return _err('An unexpected error occurred.', code='INTERNAL_ERROR', http_status=500)


# ── MPS: apply (after 3DS redirect) ──────────────────────────────────── #

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def mps_apply(request):
    s = MpsApplySerializer(data=request.data)
    if not s.is_valid():
        return _err(_first_error(s), code='VALIDATION_ERROR')

    try:
        txn = AtmosTransaction.objects.get(transaction_id=s.validated_data['transaction_id'])
    except AtmosTransaction.DoesNotExist:
        return _err('Transaction not found.', code='NOT_FOUND', http_status=404)

    service = AtmosService()
    try:
        result = service.mps_apply(txn.transaction_id)
        txn.status       = PaymentStatus.SUCCESS
        txn.raw_response = {**txn.raw_response, 'apply': result['raw']}
        txn.save()

        try:
            from click.models import Order
            order = Order.objects.select_related('membership').get(id=int(txn.account), membership__isnull=False)
            order.status = 'paid'
            order.save(update_fields=['status', 'updated_at'])
            payload  = result['raw'].get('payload') or {}
            ofd_url  = payload.get('ofd_redirect_uri') or payload.get('ofd_commission_uri', '')
            _notify_success(order, txn, ofd_url)
        except Exception:
            pass

        logger.info('mps_apply | SUCCESS | transaction_id=%s', txn.transaction_id)
        return _ok({'transaction_id': txn.transaction_id, 'message': 'Payment completed successfully.'})

    except AtmosError as exc:
        txn.status        = PaymentStatus.FAILED
        txn.error_message = str(exc)
        txn.save()
        logger.error('mps_apply | AtmosError: %s', exc)
        return _err(str(exc), code=exc.code, http_status=status.HTTP_502_BAD_GATEWAY)

    except Exception:
        logger.exception('mps_apply | unexpected error')
        return _err('An unexpected error occurred.', code='INTERNAL_ERROR', http_status=500)


# ── API: detail ──────────────────────────────────────────────────────── #

@api_view(['GET'])
@permission_classes([AllowAny])
def transaction_detail(request, transaction_id):
    try:
        txn = AtmosTransaction.objects.get(transaction_id=transaction_id)
    except AtmosTransaction.DoesNotExist:
        return _err('Transaction not found.', code='NOT_FOUND', http_status=404)
    return _ok({'transaction': AtmosTransactionSerializer(txn).data})
