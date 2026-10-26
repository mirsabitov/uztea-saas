from django.contrib import admin
from .models import PaymeTransaction


@admin.register(PaymeTransaction)
class PaymeTransactionAdmin(admin.ModelAdmin):
    list_display  = ('transaction_id', 'order', 'amount', 'state', 'created_at', 'performed_at')
    list_filter   = ('state',)
    search_fields = ('transaction_id', 'order__id')
    readonly_fields = ('transaction_id', 'order', 'amount', 'created_at', 'performed_at', 'cancelled_at')
