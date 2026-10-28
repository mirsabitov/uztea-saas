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


LANGUAGE_CHOICES = [('en', 'English'), ('uz', "O'zbekcha"), ('ru', 'Русский')]


class OrganizationSettings(models.Model):
    """Single row with the organisation's details (SaaS Settings)."""
    name = models.CharField(max_length=255, default='Uzbekistan Teachers of English Association')
    short_name = models.CharField(max_length=50, default='UzTEA')
    tagline = models.CharField(max_length=255, blank=True, default='Empowering teachers, stronger together')
    email = models.EmailField(blank=True, default='info@uztea.uz')
    phone = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True, default='https://www.uztea.uz')
    address = models.TextField(blank=True)
    logo_light = models.ImageField(upload_to='branding/', blank=True,
                                   help_text='Logo for light backgrounds (default: navy UzTEA logo).')
    logo_dark = models.ImageField(upload_to='branding/', blank=True,
                                  help_text='Logo for dark backgrounds, e.g. the sidebar (default: white UzTEA logo).')
    logo_accent = models.ImageField(upload_to='branding/', blank=True, help_text='Accent logo (default: blue UzTEA logo).')
    default_language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en',
                                        help_text='Language of the workspace, member cabinet and certificate portal '
                                                  'unless a person picks another one.')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Organisation settings'
        verbose_name_plural = 'Organisation settings'

    def __str__(self):
        return self.short_name or self.name

    @classmethod
    def get(cls):
        obj = cls.objects.order_by('pk').first()
        return obj or cls.objects.create()

    def logo_urls(self):
        """Uploaded logos, falling back to the original UzTEA files."""
        from django.templatetags.static import static
        return {
            'light': self.logo_light.url if self.logo_light else static('workspace/img/logo-navy.png'),
            'dark': self.logo_dark.url if self.logo_dark else static('workspace/img/logo-white.png'),
            'accent': self.logo_accent.url if self.logo_accent else static('workspace/img/logo-blue.png'),
        }


class Event(models.Model):
    """An UzTEA event shown to members as "upcoming". Registration stays on its own form for now."""
    KIND_CHOICES = [('conference', 'Conference'), ('workshop', 'Workshop / seminar'),
                    ('webinar', 'Webinar'), ('celebration', 'Celebration'), ('other', 'Other')]

    title = models.CharField(max_length=255)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='workshop')
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, help_text='Venue or "Online".')
    registration_url = models.URLField(blank=True, help_text='Public registration page, if any.')
    is_published = models.BooleanField(default=False, help_text='Published events are shown in member cabinets.')
    members_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['starts_at']

    def __str__(self):
        return self.title


class Benefit(models.Model):
    """A bonus, discount or offer for members (often from a partner)."""
    title = models.CharField(max_length=255)
    partner = models.ForeignKey('app.Partner', null=True, blank=True, on_delete=models.SET_NULL, related_name='benefits')
    description = models.TextField(blank=True)
    discount = models.CharField(max_length=100, blank=True, help_text='e.g. "20% off" or "Free entry".')
    code = models.CharField(max_length=100, blank=True, help_text='Promo code members show or enter.')
    link = models.URLField(blank=True)
    membership_types = models.CharField(max_length=255, blank=True,
                                        help_text='Comma-separated membership type codes. Empty = all members.')
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def type_codes(self):
        return [c.strip() for c in self.membership_types.split(',') if c.strip()]

    def applies_to(self, membership_type):
        codes = self.type_codes()
        return not codes or membership_type in codes
