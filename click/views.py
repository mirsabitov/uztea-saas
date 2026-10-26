import json
from decimal import Decimal

from django.http import JsonResponse, Http404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from .models import Order, PromoCode
from .utils import (
    build_membership_card_context,
    verify_click_signature,
    get_click_url,
    get_card_payment_url,
    submit_fiscal_data_async,
)
from django.shortcuts import render, get_object_or_404, redirect
import logging

logger = logging.getLogger('click')


@csrf_exempt
def click_webhook(request):
    try:
        return _click_webhook_inner(request)
    except Exception as exc:
        logger.exception("Unhandled exception in click_webhook: %s", exc)
        return JsonResponse({"error": -3, "error_note": "Internal server error"})


def _click_webhook_inner(request):
    if request.method != 'POST':
        return JsonResponse({"error": -3, "error_note": "Method not allowed"})

    # --- Read raw body and headers for debug logging ---
    raw_body = request.body
    content_type = (request.content_type or '').lower()

    is_simulated = request.headers.get('X-Click-Simulated') == '1'
    log_tag = '[SIM_API]' if is_simulated else '[REAL_API]'

    logger.info(f"{log_tag} Raw content_type={content_type}")
    logger.info(f"{log_tag} Raw body: {raw_body!r}")
    logger.info(
        f"{log_tag} Headers: X-Forwarded-For={request.META.get('HTTP_X_FORWARDED_FOR')}, "
        f"X-Click-Simulated={request.META.get('HTTP_X_CLICK_SIMULATED')}, "
        f"User-Agent={request.META.get('HTTP_USER_AGENT')}"
    )

    # Normalize payload to a plain dict of strings
    if content_type.startswith('application/json'):
        import json as _json
        try:
            parsed = _json.loads(raw_body.decode('utf-8') or '{}')
        except Exception:
            logger.error(f"{log_tag} Invalid JSON payload")
            return JsonResponse({"error": -3, "error_note": "Invalid JSON"})
        params = {k: str(v) if v is not None else '' for k, v in parsed.items()}
    else:
        # request.POST is a QueryDict — convert to simple key->value strings
        params = {k: request.POST.get(k) for k in request.POST.keys()}

    action = params.get('action')
    logger.info(f"{log_tag} Received Click Webhook: Action={action}, Params keys={list(params.keys())}")

    if not verify_click_signature(params):
        incoming_sign = params.get('sign_string') or params.get('sign') or '<missing>'
        logger.error(
            f"{log_tag} Click Signature verification failed. incoming_sign={incoming_sign} params_keys={list(params.keys())}")
        return JsonResponse({"error": -1, "error_note": "Signature verification failed"})

    merchant_trans_id = params.get('merchant_trans_id')
    amount = float(params.get('amount') or 0)
    click_trans_id = int(float(params.get('click_trans_id') or 0))

    try:
        order = Order.objects.get(id=merchant_trans_id, membership__isnull=False)
    except Order.DoesNotExist:
        logger.error(f"{log_tag} Order #{merchant_trans_id} not found")
        return JsonResponse({"error": -5, "error_note": "Order not found"})

    if action == '0':  # Prepare
        if abs(float(order.amount) - amount) > 0.01:
            logger.warning(f"{log_tag} Order #{order.id}: Incorrect amount. Expected {order.amount}, got {amount}")
            response_data = {"error": -2, "error_note": "Incorrect amount"}
            logger.info(f"{log_tag} Prepare response for Order #{order.id}: {response_data}")
            return JsonResponse(response_data)

        if order.status == 'paid':
            response_data = {"error": -4, "error_note": "Already paid"}
            logger.info(f"{log_tag} Prepare response for Order #{order.id}: {response_data}")
            return JsonResponse(response_data)

        order.status = 'processing'
        order.click_trans_id = str(click_trans_id)
        order.save()

        response_data = {
            "error": 0,
            "error_note": "Success",
            "click_trans_id": click_trans_id,
            "merchant_trans_id": order.id,
            "merchant_prepare_id": order.id,
        }
        logger.info(f"{log_tag} Prepare response for Order #{order.id}: {response_data}")
        return JsonResponse(response_data)

    elif action == '1':  # Complete
        error = params.get('error')

        if error != '0':
            logger.error(f"{log_tag} Order #{order.id}: Transaction failed with Click error code {error}")
            order.status = 'failed'
            order.click_trans_id = str(click_trans_id)
            order.click_paydoc_id = params.get('click_paydoc_id')
            order.save()
            response_data = {
                "error": 0,
                "error_note": "Success",
                "click_trans_id": click_trans_id,
                "merchant_trans_id": order.id,
                "merchant_confirm_id": order.id,
            }
            logger.info(f"{log_tag} Complete (failed) response for Order #{order.id}: {response_data}")
            return JsonResponse(response_data)

        # Prepare chaqirilganini tekshirish
        if order.status != 'processing':
            logger.error(f"{log_tag} Order #{order.id}: Unexpected status '{order.status}' on Complete")
            return JsonResponse({"error": -9, "error_note": "Transaction cancelled"})

        # merchant_prepare_id Click tomonidan qaytarilgan order.id ga mos kelishini tekshirish
        merchant_prepare_id = params.get('merchant_prepare_id')
        if str(merchant_prepare_id) != str(order.id):
            logger.error(f"{log_tag} Order #{order.id}: merchant_prepare_id mismatch. Got {merchant_prepare_id}")
            return JsonResponse({"error": -6, "error_note": "merchant_prepare_id does not match"})

        # Mark as paid
        order.status = 'paid'
        order.click_trans_id = str(click_trans_id)
        order.click_paydoc_id = params.get('click_paydoc_id')
        order.save()

        logger.info(f"{log_tag} Order #{order.id} paid successfully.")

        from app.notifications import (
            send_membership_purchase_notification_async,
            send_membership_welcome_email_async,
        )
        send_membership_purchase_notification_async(order.id, source='Click')
        send_membership_welcome_email_async(order.id)
        submit_fiscal_data_async(order.id)

        response_data = {
            "error": 0,
            "error_note": "Success",
            "click_trans_id": click_trans_id,
            "merchant_trans_id": order.id,
            "merchant_confirm_id": order.id,
        }
        logger.info(f"{log_tag} Complete response for Order #{order.id}: {response_data}")
        return JsonResponse(response_data)

    return JsonResponse({"error": -3, "error_note": "Unknown action"})


@csrf_exempt
def apply_promocode(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    order_id = payload.get('order_id')
    code = (payload.get('code') or '').strip()

    if not order_id or not code:
        return JsonResponse({'success': False, 'error': 'Order and promocode are required.'}, status=400)

    try:
        order = Order.objects.select_related('membership').get(id=int(order_id), membership__isnull=False)
    except (Order.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Order not found.'}, status=404)

    if order.status == 'paid':
        return JsonResponse({
            'success': True,
            'paid': True,
            'status_url': reverse('payment_status', args=[order.pk]),
        })

    try:
        promo = PromoCode.objects.get(code__iexact=code)
    except PromoCode.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid promocode.'}, status=400)

    usable, reason = promo.is_usable()
    if not usable:
        return JsonResponse({'success': False, 'error': reason}, status=400)

    percent = min(int(promo.discount_percent), 100)
    order.promocode = promo

    if percent >= 100:
        # Full free — mark paid and skip payment entirely.
        order.amount = Decimal('0.00')
        order.status = 'paid'
        order.save(update_fields=['amount', 'status', 'promocode', 'updated_at'])
        promo.used_count = promo.used_count + 1
        promo.save(update_fields=['used_count'])
        from app.notifications import (
            send_membership_purchase_notification_async,
            send_membership_welcome_email_async,
        )
        send_membership_welcome_email_async(order.id)
        send_membership_purchase_notification_async(order.id, source=f'Promocode: {promo.code}')
        logger.info('promocode | order #%s fully paid with code %s', order.id, promo.code)
        return JsonResponse({
            'success': True,
            'paid': True,
            'status_url': reverse('payment_status', args=[order.pk]),
        })

    # Partial discount — reduce amount and let the user pay the rest normally.
    new_amount = (order.amount * Decimal(100 - percent) / Decimal(100)).quantize(Decimal('0.01'))
    order.amount = new_amount
    order.save(update_fields=['amount', 'promocode', 'updated_at'])
    promo.used_count = promo.used_count + 1
    promo.save(update_fields=['used_count'])
    logger.info('promocode | order #%s discounted %s%% with code %s', order.id, percent, promo.code)
    return JsonResponse({
        'success': True,
        'paid': False,
        'discount_percent': percent,
        'amount': float(new_amount),
        'amount_tiyin': int(float(new_amount) * 100),
    })


def membership_payment(request, order_pk):
    order = get_object_or_404(Order, pk=order_pk, membership__isnull=False)
    if order.status == 'paid':
        return redirect('payment_status', order_pk=order.pk)

    from payme.views import generate_payme_url
    amount_tiyin = int(float(order.amount) * 100)
    atmos_url = f'/payments/atmos/pay/?order={order.id}&amount={amount_tiyin}'

    return render(request, 'payment_page.html', {
        'order': order,
        'membership': order.membership,
        'payme_url': generate_payme_url(order),
        'atmos_url': atmos_url,
    })


def payment_status(request, order_pk):
    try:
        order = get_object_or_404(Order, pk=order_pk, membership__isnull=False)
        membership = order.membership

        # Always show membership card regardless of payment status
        member_url = request.build_absolute_uri(reverse('payment_status', args=[order.pk]))
        ctx = build_membership_card_context(membership, order, member_url)
        ctx['redirect_on_status_navigation'] = True
        ctx['status_redirect_url'] = 'https://uztea.uz/'
        return render(request, 'membership-card.html', ctx)
    except Exception:
        logger.exception('payment_status | failed to render card | order_pk=%s', order_pk)
        raise


def team_member_card(request, order_pk, idx):
    """Render a membership card for an institutional team member (idx = 2..5)."""
    from types import SimpleNamespace
    try:
        order = get_object_or_404(Order, pk=order_pk, membership__isnull=False)
        membership = order.membership

        if idx not in (2, 3, 4, 5):
            raise Http404('Invalid member index.')

        name = getattr(membership, f'member_{idx}_name', None)
        email = getattr(membership, f'member_{idx}_email', None)
        if not name:
            raise Http404('Member not found.')

        # Proxy membership object: team member identity, institution-level details inherited
        proxy = SimpleNamespace(
            id=membership.id,
            full_name=name,
            email=email or '',
            phone_number='',
            country=membership.country,
            region_city=membership.region_city,
            institution_name=membership.institution_name,
            contact_person_name=None,
            contact_person_email=None,
            get_membership_type_display=membership.get_membership_type_display,
        )
        member_url = request.build_absolute_uri(
            reverse('team_member_card', args=[order.pk, idx])
        )
        card_id = f'UZ{membership.id:06d}-{idx - 1}'
        ctx = build_membership_card_context(
            proxy, order, member_url, card_id_override=card_id
        )
        ctx['redirect_on_status_navigation'] = True
        ctx['status_redirect_url'] = 'https://uztea.uz/'
        return render(request, 'membership-card.html', ctx)
    except Http404:
        raise
    except Exception:
        logger.exception('team_member_card | failed | order_pk=%s idx=%s', order_pk, idx)
        raise
