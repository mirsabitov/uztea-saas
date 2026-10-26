from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import AtmosTransaction, PaymentStatus, PaymentType
from .services.atmos import AtmosError, AtmosService


@admin.register(AtmosTransaction)
class AtmosTransactionAdmin(admin.ModelAdmin):
    list_display  = [
        'transaction_id',
        'account',
        'amount_uzs_display',
        'status',
        'card_number_masked',
        'created_at',
        'cancel_payment_link',
    ]
    list_filter   = ['status', 'created_at']
    search_fields = ['transaction_id', 'account', 'card_number_masked', 'atmos_transaction_id']
    readonly_fields = [
        'id',
        'transaction_id',
        'atmos_transaction_id',
        'created_at',
        'updated_at',
        'raw_request',
        'raw_response',
        'cancel_payment_link',
    ]
    ordering      = ['-created_at']

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<uuid:transaction_pk>/cancel/',
                self.admin_site.admin_view(self.cancel_payment_view),
                name='atmos_atmostransaction_cancel',
            ),
        ]
        return custom + urls

    @admin.display(description='Amount (UZS)')
    def amount_uzs_display(self, obj):
        return f'{obj.amount_uzs:,.2f} UZS'

    @admin.display(description='Cancel payment')
    def cancel_payment_link(self, obj):
        if obj is None or not self._can_cancel(obj):
            return '-'
        url = reverse('admin:atmos_atmostransaction_cancel', args=[obj.pk])
        return format_html('<a class="button" href="{}">Cancel payment</a>', url)

    def cancel_payment_view(self, request, transaction_pk):
        transaction = self.get_object(request, str(transaction_pk))
        if transaction is None:
            messages.error(request, 'ATMOS transaction topilmadi.')
            return HttpResponseRedirect(reverse('admin:atmos_atmostransaction_changelist'))

        if not self.has_change_permission(request, transaction):
            raise PermissionDenied

        change_url = reverse('admin:atmos_atmostransaction_change', args=[transaction.pk])

        if request.method == 'POST':
            reason = request.POST.get('reason', '').strip() or 'Cancelled from Django admin'
            if not self._can_cancel(transaction):
                messages.warning(request, 'Faqat SUCCESS holatdagi UzCard/Humo ATMOS tranzaksiyalar bekor qilinadi.')
                return HttpResponseRedirect(change_url)

            service = AtmosService()
            try:
                result = service.reverse_payment(transaction.transaction_id, reason)
            except AtmosError as exc:
                transaction.error_message = str(exc)
                transaction.raw_response = {
                    **self._raw_response(transaction),
                    'reverse_error': exc.raw or {'message': str(exc), 'code': exc.code},
                }
                transaction.save(update_fields=['error_message', 'raw_response', 'updated_at'])
                messages.error(request, f'Atmos cancellation failed: {exc}')
                return HttpResponseRedirect(change_url)

            transaction.status = PaymentStatus.CANCELLED
            transaction.error_message = ''
            transaction.raw_response = {
                **self._raw_response(transaction),
                'reverse': result['raw'],
            }
            transaction.save(update_fields=['status', 'error_message', 'raw_response', 'updated_at'])
            order_message = self._mark_related_order_failed(transaction)
            success_message = f'ATMOS transaction {transaction.transaction_id} bekor qilindi.'
            if order_message:
                success_message = f'{success_message} {order_message}'
            messages.success(request, success_message)
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            'title': 'Cancel ATMOS payment',
            'opts': self.model._meta,
            'transaction': transaction,
            'change_url': change_url,
            'default_reason': 'Cancelled from Django admin',
        }
        return TemplateResponse(request, 'admin/atmos/atmostransaction/cancel_payment.html', context)

    @staticmethod
    def _can_cancel(obj):
        return obj.status == PaymentStatus.SUCCESS and obj.payment_type == PaymentType.UZCARD

    @staticmethod
    def _raw_response(obj):
        return obj.raw_response if isinstance(obj.raw_response, dict) else {}

    @staticmethod
    def _mark_related_order_failed(transaction):
        try:
            order_id = int(transaction.account)
        except (TypeError, ValueError):
            return ''

        try:
            from click.models import Order
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return ''

        if order.status != 'paid':
            return f'Order #{order.id} status ozgarmadi ({order.status}).'

        order.status = 'failed'
        order.save(update_fields=['status', 'updated_at'])
        return f'Order #{order.id} status failed qilib yangilandi.'
