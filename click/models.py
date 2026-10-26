from django.db import models
from django.conf import settings
from django.utils import timezone
from app.models import Membership


class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.PositiveSmallIntegerField(
        default=100,
        help_text='100 = full free. Later set 50 or 30 for partial discount.',
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True, help_text='Empty = never expires')
    max_uses = models.PositiveIntegerField(blank=True, null=True, help_text='Empty = unlimited')
    used_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Promo Code'
        verbose_name_plural = 'Promo Codes'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code} (-{self.discount_percent}%)'

    def is_usable(self):
        if not self.is_active:
            return False, 'This promocode is not active.'
        if self.expires_at and timezone.now() > self.expires_at:
            return False, 'This promocode has expired.'
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False, 'This promocode has reached its usage limit.'
        return True, ''


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='orders', null=True, blank=True)
    conference_registration = models.OneToOneField(
        'app.ConferenceRegistration', on_delete=models.CASCADE, related_name='order', null=True, blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Click specific fields
    click_trans_id = models.CharField(max_length=255, blank=True, null=True)
    click_paydoc_id = models.CharField(max_length=255, blank=True, null=True)

    # Promocode applied to this order (if any)
    promocode = models.ForeignKey(
        'PromoCode', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} - {self.status}"

    @property
    def payme_account_id(self):
        return self.membership_id or self.conference_registration_id
