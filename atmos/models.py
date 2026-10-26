import uuid
from django.db import models


class PaymentStatus(models.TextChoices):
    PENDING   = 'PENDING',   'Pending'
    OTP_SENT  = 'OTP_SENT',  'OTP Sent'
    CARD_BOUND = 'CARD_BOUND', 'Card Bound'
    SUCCESS   = 'SUCCESS',   'Success'
    FAILED    = 'FAILED',    'Failed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PaymentType(models.TextChoices):
    UZCARD = 'uzcard', 'UzCard / Humo'
    MPS    = 'mps',    'Visa / Mastercard'


class AtmosTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id       = models.CharField(max_length=255, unique=True, db_index=True)
    atmos_transaction_id = models.CharField(max_length=255, blank=True)
    amount               = models.PositiveBigIntegerField(help_text='Tiyinlarda (1 UZS = 100 tiyin)')
    account              = models.CharField(max_length=255, help_text='Order ID yoki referens (faqat raqamlar)')
    card_number_masked   = models.CharField(max_length=20, blank=True)
    store_id             = models.CharField(max_length=255, blank=True)
    payment_type         = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.UZCARD)
    mps_card_id          = models.CharField(max_length=255, blank=True)
    status               = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    error_message = models.TextField(blank=True)
    raw_request   = models.JSONField(default=dict, blank=True)
    raw_response  = models.JSONField(default=dict, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'ATMOS Transaction'
        verbose_name_plural = 'ATMOS Transactions'

    def __str__(self):
        return f'{self.transaction_id} | {self.status} | {self.amount_uzs} UZS'

    @property
    def amount_uzs(self):
        return self.amount / 100

    @staticmethod
    def mask_card(card_number: str) -> str:
        cleaned = card_number.replace(' ', '')
        if len(cleaned) >= 8:
            return cleaned[:4] + ' **** **** ' + cleaned[-4:]
        return cleaned
