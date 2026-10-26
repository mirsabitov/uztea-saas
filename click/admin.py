import hashlib
import time
import json
import urllib.request
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import JsonResponse
from django.utils.html import format_html
from django.urls import reverse, path
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.test import RequestFactory

from app.models import Membership
from app.pricing import get_membership_price
from .views import click_webhook
from .models import Order, PromoCode
from .utils import get_click_url, get_card_payment_url

def check_payment_status(order):
    merchant_user_id = os.getenv('CLICK_MERCHANT_USER_ID', '')
    service_id = os.getenv('CLICK_SERVICE_ID', '')
    secret_key = os.getenv('CLICK_SECRET_KEY', '')

    ts = str(int(time.time()))
    digest = hashlib.sha1(f'{ts}{secret_key}'.encode()).hexdigest()
    auth = f'{merchant_user_id}:{digest}:{ts}'

    url = f'https://api.click.uz/v2/merchant/payment/status/{service_id}/{order.click_trans_id}'
    req = urllib.request.Request(url)
    req.add_header('Auth', auth)
    req.add_header('Accept', 'application/json')

    try:
        res = urllib.request.urlopen(req, timeout=10)
        return json.loads(res.read())
    except Exception as e:
        return {'error': str(e)}


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_percent', 'is_active', 'used_count', 'max_uses', 'expires_at', 'created_at')
    list_filter = ('is_active', 'discount_percent')
    search_fields = ('code',)
    readonly_fields = ('used_count', 'created_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'membership', 'conference_registration', 'amount', 'status', 'click_trans_id', 'payment_link', 'check_button', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('membership__full_name', 'click_trans_id')
    readonly_fields = ('created_at', 'updated_at', 'payment_buttons')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('membership')

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('tools/', self.admin_site.admin_view(self.tools_view), name='click_order_tools'),
            path('tools/logs/', self.admin_site.admin_view(self.logs_api_view), name='click_order_tools_logs_api'),
            path('tools/simulate/', self.admin_site.admin_view(self.simulate_view), name='click_order_simulate'),
            path('tools/create-order/', self.admin_site.admin_view(self.create_order_view), name='click_order_create_order'),
            path('<int:order_id>/check/', self.admin_site.admin_view(self.check_view), name='click_order_check'),
        ]
        return custom + urls

    def tools_view(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied

        try:
            lines_limit = int(request.GET.get('lines', 300))
        except (TypeError, ValueError):
            lines_limit = 300
        lines_limit = min(max(lines_limit, 50), 1000)

        status_counts = {
            row['status']: row['total']
            for row in Order.objects.values('status').annotate(total=Count('id'))
        }
        orders = Order.objects.select_related('membership').order_by('-created_at')[:20]
        memberships = Membership.objects.filter(payment_method='click').order_by('-created_at')[:300]

        context = {
            **self.admin_site.each_context(request),
            'title': 'Click Tools & Logs',
            'opts': self.model._meta,
            'orders': orders,
            'status_counts': status_counts,
            'total_orders': sum(status_counts.values()),
            'webhook_url': request.build_absolute_uri(reverse('click_webhook')),
            'simulate_url': reverse('admin:click_order_simulate'),
            'create_order_url': reverse('admin:click_order_create_order'),
            'logs_api_url': reverse('admin:click_order_tools_logs_api'),
            'log_file_path': Path(settings.BASE_DIR) / 'click_payments.log',
            'log_entries': self._read_log_entries(lines_limit, real_only=True),
            'lines_limit': lines_limit,
            'memberships': memberships,
        }
        return TemplateResponse(request, 'admin/click/tools.html', context)

    def logs_api_view(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied

        try:
            lines_limit = int(request.GET.get('lines', 300))
        except (TypeError, ValueError):
            lines_limit = 300
        lines_limit = min(max(lines_limit, 50), 1000)

        status_counts = {
            row['status']: row['total']
            for row in Order.objects.values('status').annotate(total=Count('id'))
        }

        return JsonResponse(
            {
                'entries': self._read_log_entries(lines_limit, real_only=True),
                'status_counts': status_counts,
                'total_orders': sum(status_counts.values()),
                'lines_limit': lines_limit,
                'server_time': int(time.time()),
            }
        )

    def simulate_view(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        if request.method != 'POST':
            return HttpResponseRedirect(reverse('admin:click_order_tools'))

        order_id = request.POST.get('order_id')
        mode = request.POST.get('mode')
        redirect_url = reverse('admin:click_order_tools')

        if not order_id:
            messages.error(request, "order_id topilmadi.")
            return HttpResponseRedirect(redirect_url)

        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            messages.error(request, f"Order #{order_id} topilmadi.")
            return HttpResponseRedirect(redirect_url)

        click_trans_id = str(int(time.time()))

        if mode == 'prepare':
            result = self._simulate_prepare(order, click_trans_id)
            messages.info(request, f"Prepare test: {result}")
        elif mode == 'complete_paid':
            prepare_result = None
            if order.status != 'processing':
                prepare_result = self._simulate_prepare(order, click_trans_id)
            complete_result = self._simulate_complete(order, click_trans_id, error='0')
            messages.success(
                request,
                f"Complete paid test. Prepare={prepare_result} | Complete={complete_result}",
            )
        elif mode == 'complete_failed':
            result = self._simulate_complete(order, click_trans_id, error='-501')
            messages.warning(request, f"Complete failed test: {result}")
        else:
            messages.error(request, f"Noma'lum mode: {mode}")

        return HttpResponseRedirect(redirect_url)

    def create_order_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        if request.method != 'POST':
            return HttpResponseRedirect(reverse('admin:click_order_tools'))

        membership_id = request.POST.get('membership_id')
        amount_raw = (request.POST.get('amount') or '').strip()
        redirect_url = reverse('admin:click_order_tools')

        if not membership_id:
            messages.error(request, "Membership tanlanmadi.")
            return HttpResponseRedirect(redirect_url)

        try:
            membership = Membership.objects.get(pk=membership_id)
        except Membership.DoesNotExist:
            messages.error(request, f"Membership #{membership_id} topilmadi.")
            return HttpResponseRedirect(redirect_url)

        if amount_raw:
            try:
                amount = Decimal(amount_raw)
            except InvalidOperation:
                messages.error(request, "Amount noto'g'ri formatda.")
                return HttpResponseRedirect(redirect_url)
        else:
            amount = Decimal(str(get_membership_price(membership.membership_type)))

        order = Order.objects.create(
            membership=membership,
            amount=amount,
            user=request.user if request.user.is_authenticated else None,
        )
        messages.success(
            request,
            f"Order #{order.id} yaratildi. Membership: {membership.full_name}, amount: {order.amount}",
        )
        return HttpResponseRedirect(redirect_url)

    def _read_log_entries(self, limit=300, real_only=False):
        log_path = Path(settings.BASE_DIR) / 'click_payments.log'
        if not log_path.exists():
            return []

        with log_path.open('r', encoding='utf-8', errors='ignore') as log_file:
            lines = log_file.readlines()[-limit:]

        entries = []
        for line in lines:
            clean_line = line.rstrip()
            if not clean_line:
                continue
            if real_only and '[REAL_API]' not in clean_line:
                continue
            entries.append(
                {
                    'line': clean_line,
                    'level': self._detect_log_level(clean_line),
                }
            )
        return entries

    @staticmethod
    def _detect_log_level(line):
        upper = line.upper()
        if 'ERROR' in upper:
            return 'error'
        if 'WARNING' in upper:
            return 'warning'
        if 'INFO' in upper:
            return 'info'
        return 'other'

    def _simulate_prepare(self, order, click_trans_id):
        payload = self._build_signed_payload(
            order=order,
            action='0',
            click_trans_id=click_trans_id,
            error='0',
            merchant_prepare_id='',
        )
        return self._call_webhook(payload)

    def _simulate_complete(self, order, click_trans_id, error='0'):
        payload = self._build_signed_payload(
            order=order,
            action='1',
            click_trans_id=click_trans_id,
            error=error,
            merchant_prepare_id=str(order.id),
        )
        return self._call_webhook(payload)

    @staticmethod
    def _call_webhook(payload):
        factory = RequestFactory()
        req = factory.post('/payments/click/webhook/', data=payload, HTTP_X_CLICK_SIMULATED='1')
        response = click_webhook(req)

        try:
            body = json.loads(response.content.decode('utf-8'))
        except Exception:
            body = {'error': -999, 'error_note': 'Unexpected response format'}
        return body

    @staticmethod
    def _build_signed_payload(order, action, click_trans_id, error='0', merchant_prepare_id=''):
        service_id = os.getenv('CLICK_SERVICE_ID', '')
        secret_key = os.getenv('CLICK_SECRET_KEY', '')
        sign_time = str(int(time.time()))
        amount_str = format(order.amount, 'f')

        payload = {
            'click_trans_id': str(click_trans_id),
            'service_id': str(service_id),
            'merchant_trans_id': str(order.id),
            'amount': amount_str,
            'action': str(action),
            'error': str(error),
            'sign_time': sign_time,
        }

        if str(action) == '1':
            payload['merchant_prepare_id'] = str(merchant_prepare_id or order.id)
            payload['click_paydoc_id'] = str(click_trans_id)
            sign_source = (
                f"{payload['click_trans_id']}{payload['service_id']}{secret_key}"
                f"{payload['merchant_trans_id']}{payload['merchant_prepare_id']}"
                f"{payload['amount']}{payload['action']}{payload['sign_time']}"
            )
        else:
            sign_source = (
                f"{payload['click_trans_id']}{payload['service_id']}{secret_key}"
                f"{payload['merchant_trans_id']}{payload['amount']}"
                f"{payload['action']}{payload['sign_time']}"
            )

        payload['sign_string'] = hashlib.md5(sign_source.encode('utf-8')).hexdigest()
        return payload

    def check_view(self, request, order_id):
        order = Order.objects.get(pk=order_id)

        if not order.click_trans_id:
            messages.warning(request, f"Order #{order.id}: click_trans_id yo'q — hali to'lov qilinmagan.")
        else:
            res = check_payment_status(order)
            payment_status = res.get('payment_status')

            STATUS_MAP = {
                2: ('paid', "To'landi"),
                -1: ('failed', 'Bekor qilindi'),
                -2: ('failed', 'Qaytarildi'),
            }

            if payment_status in STATUS_MAP:
                new_status, label = STATUS_MAP[payment_status]
                order.status = new_status
                order.save()
                messages.success(request, f"Order #{order.id}: {label} — status yangilandi.")
            else:
                messages.info(request, f"Order #{order.id}: payment_status={payment_status} | {res}")

        return HttpResponseRedirect(reverse('admin:click_order_changelist'))

    def check_button(self, obj):
        url = reverse('admin:click_order_check', args=[obj.pk])
        if obj.status == 'paid':
            return format_html('<span style="color:green;">✔ Tolangan</span>')
        return format_html(
            '<a href="{}" style="background:#ff9800;color:#fff;padding:4px 10px;border-radius:4px;text-decoration:none;font-size:12px;">Check</a>',
            url
        )
    check_button.short_description = 'Status check'

    def payment_link(self, obj):
        if obj.conference_registration_id:
            url = reverse('conference_payment', args=[obj.conference_registration.payment_token])
            return format_html('<a href="{}">TESOL payment</a>', url)
        if obj.status == 'paid':
            return format_html('<span style="color:green;">✔ Tolangan</span>')
        url = reverse('membership_payment', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">To\'lov sahifasi</a>', url)
    payment_link.short_description = "To'lov"

    def payment_buttons(self, obj):
        if obj.conference_registration_id:
            return self.payment_link(obj)
        if obj.status == 'paid':
            return format_html('<span style="color:green; font-weight:bold;">✔ To\'lov amalga oshirilgan</span>')
        click_url = get_click_url(obj.id, obj.amount)
        card_url = get_card_payment_url(obj.id, obj.amount)
        return format_html(
            '<a href="{}" target="_blank" style="background:#1a73e8;color:#fff;padding:6px 14px;border-radius:4px;text-decoration:none;margin-right:8px;">Click orqali</a>'
            '<a href="{}" target="_blank" style="background:#34a853;color:#fff;padding:6px 14px;border-radius:4px;text-decoration:none;">Karta orqali</a>',
            click_url, card_url
        )
    payment_buttons.short_description = "To'lov tugmalari"
