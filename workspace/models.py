from django.conf import settings
from django.db import models


class MessageLog(models.Model):
    """One SMS or email sent (or attempted) from the workspace.

    Permissions: add_messagelog = may send, view_messagelog = may see the history.
    """
    CHANNEL_SMS = 'sms'
    CHANNEL_EMAIL = 'email'
    CHANNEL_CHOICES = [(CHANNEL_SMS, 'SMS'), (CHANNEL_EMAIL, 'Email')]

    SENT = 'sent'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    TEST = 'test'
    STATUS_CHOICES = [
        (SENT, 'Sent'),
        (FAILED, 'Failed'),
        (SKIPPED, 'Skipped'),
        (TEST, 'Test mode (not sent)'),
    ]

    batch = models.UUIDField(db_index=True, help_text='Messages sent together share a batch id.')
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    source = models.CharField(max_length=40, help_text='Recipient list, e.g. member, partner, teachers_bank.')
    recipient_id = models.PositiveIntegerField(null=True, blank=True)
    recipient_name = models.CharField(max_length=255, blank=True)
    to = models.CharField(max_length=255, blank=True, help_text='Phone number or email address.')
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    provider_id = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        indexes = [models.Index(fields=['source', 'recipient_id'])]

    def __str__(self):
        return f'{self.get_channel_display()} to {self.to or self.recipient_name} ({self.status})'
