from django.conf import settings
from django.db import models
from click.models import Order


class PaymeConfig(models.Model):
    """Payme secret key ni dinamik saqlash (ChangePassword uchun)"""
    secret_key = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payme Config'

    def __str__(self):
        return f"PaymeConfig (updated: {self.updated_at})"

    @classmethod
    def get_secret_key(cls):
        config = cls.objects.first()
        if config:
            return config.secret_key
        return settings.PAYME_SECRET_KEY

    @classmethod
    def set_secret_key(cls, new_key):
        config = cls.objects.first()
        if config:
            config.secret_key = new_key
            config.save()
        else:
            cls.objects.create(secret_key=new_key)


class PaymeTransaction(models.Model):
    STATE_CHOICES = (
        (1,  'Waiting'),
        (2,  'Paid'),
        (-1, 'Cancelled'),
        (-2, 'Cancelled After'),
    )
    REASON_CHOICES = (
        (1, 'User cancelled'),
        (2, 'Transaction timeout'),
        (3, 'Order unavailable'),
        (4, 'Payment failed'),
        (5, 'Unknown error'),
    )

    transaction_id = models.CharField(max_length=255, unique=True, db_index=True)
    order          = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payme_transactions')
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    state          = models.SmallIntegerField(choices=STATE_CHOICES, default=1)

    created_at     = models.DateTimeField(auto_now_add=True)
    performed_at   = models.DateTimeField(null=True, blank=True)
    cancelled_at   = models.DateTimeField(null=True, blank=True)
    reason         = models.SmallIntegerField(choices=REASON_CHOICES, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payme Transaction'
        verbose_name_plural = 'Payme Transactions'

    def __str__(self):
        return f"Transaction {self.transaction_id[:12]}... — Order #{self.order_id}"
