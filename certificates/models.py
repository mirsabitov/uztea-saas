import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

NUMBER_PREFIX = 'UZTEA'


def default_design():
    """Landscape A4 layout. Positions are % of the page; font sizes are % of the page width."""
    return [
        {'id': 'logo', 'type': 'image', 'source': 'uztea_logo', 'x': 14, 'y': 15, 'w': 11},
        {'id': 'partner', 'type': 'image', 'source': 'partner_logo', 'x': 86, 'y': 15, 'w': 11},
        {'id': 'title', 'type': 'text', 'text': 'CERTIFICATE', 'x': 50, 'y': 27, 'w': 70,
         'size': 5.2, 'weight': 800, 'color': '#222e50', 'align': 'center', 'font': 'serif', 'spacing': 0.12},
        {'id': 'subtitle', 'type': 'text', 'text': 'of participation', 'x': 50, 'y': 35.5, 'w': 80,
         'size': 2.1, 'weight': 500, 'color': '#1f6feb', 'align': 'center', 'font': 'sans', 'spacing': 0.2},
        {'id': 'presented', 'type': 'text', 'text': 'This certificate is presented to', 'x': 50, 'y': 44, 'w': 80,
         'size': 1.5, 'weight': 400, 'color': '#55627a', 'align': 'center', 'font': 'sans'},
        {'id': 'name', 'type': 'text', 'text': '{name}', 'x': 50, 'y': 53, 'w': 86,
         'size': 4.4, 'weight': 700, 'color': '#0c2247', 'align': 'center', 'font': 'serif'},
        {'id': 'body', 'type': 'text', 'text': 'for taking part in {event}, held on {date}.', 'x': 50, 'y': 63, 'w': 70,
         'size': 1.55, 'weight': 400, 'color': '#2b3a57', 'align': 'center', 'font': 'sans'},
        {'id': 'signature', 'type': 'image', 'source': 'signature', 'x': 25, 'y': 74, 'w': 16},
        {'id': 'signer', 'type': 'text', 'text': '{signer_name}\n{signer_title}', 'x': 25, 'y': 84, 'w': 30,
         'size': 1.25, 'weight': 600, 'color': '#222e50', 'align': 'center', 'font': 'sans', 'line': True},
        {'id': 'stamp', 'type': 'image', 'source': 'stamp', 'x': 42, 'y': 75, 'w': 12},
        {'id': 'number', 'type': 'text', 'text': 'No. {number}\nVerify: {verify_url}', 'x': 78, 'y': 86, 'w': 34,
         'size': 0.95, 'weight': 500, 'color': '#55627a', 'align': 'center', 'font': 'sans'},
    ]


IMAGE_SOURCES = [
    ('uztea_logo', 'UzTEA logo'), ('partner_logo', 'Partner logo'), ('extra_logo', 'Extra logo'),
    ('signature', 'Signature'), ('stamp', 'Stamp / seal'),
]
PLACEHOLDERS = [
    ('{name}', 'Recipient name'), ('{event}', 'Event'), ('{date}', 'Event / issue date'),
    ('{number}', 'Certificate number'), ('{membership_id}', 'Membership ID'),
    ('{signer_name}', 'Signer name'), ('{signer_title}', 'Signer title'), ('{verify_url}', 'Verification link'),
]


class CertificateTemplate(models.Model):
    ORIENTATIONS = [('landscape', 'Landscape (A4)'), ('portrait', 'Portrait (A4)')]

    name = models.CharField(max_length=200, help_text='Internal name, e.g. "TESOL 2026 — participant".')
    event_name = models.CharField(max_length=255, help_text='Fills {event}, e.g. "TESOL Uzbekistan 2026".')
    event = models.ForeignKey('workspace.Event', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='certificate_templates')
    date_text = models.CharField(max_length=100, blank=True, help_text='Fills {date}, e.g. "12–13 March 2026".')
    signer_name = models.CharField(max_length=150, blank=True)
    signer_title = models.CharField(max_length=150, blank=True, default='President, UzTEA')
    orientation = models.CharField(max_length=10, choices=ORIENTATIONS, default='landscape')
    accent_color = models.CharField(max_length=7, default='#1f6feb')
    frame = models.BooleanField(default=True, help_text='Draw the UzTEA frame (turn off when the background has one).')
    background = models.ImageField(upload_to='certificates/assets/', blank=True)
    partner_logo = models.ImageField(upload_to='certificates/assets/', blank=True)
    extra_logo = models.ImageField(upload_to='certificates/assets/', blank=True)
    signature = models.ImageField(upload_to='certificates/assets/', blank=True)
    stamp = models.ImageField(upload_to='certificates/assets/', blank=True)
    design = models.JSONField(default=default_design)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class CertificateSequence(models.Model):
    """One counter per year: UZTEA-<year>-<6 digits>. Numbers are never reused."""
    year = models.PositiveIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=0)

    @classmethod
    def next_number(cls, year=None):
        year = year or timezone.localdate().year
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(year=year)
            seq.last_number += 1
            seq.save(update_fields=['last_number'])
            return f'{NUMBER_PREFIX}-{year}-{seq.last_number:06d}'


class Certificate(models.Model):
    ACTIVE, REVOKED = 'active', 'revoked'
    STATUS_CHOICES = [(ACTIVE, 'Valid'), (REVOKED, 'Revoked')]

    number = models.CharField(max_length=30, unique=True, editable=False)
    template = models.ForeignKey(CertificateTemplate, on_delete=models.PROTECT, related_name='certificates')
    recipient_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, db_index=True)
    membership = models.ForeignKey('app.Membership', null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='certificates')
    source = models.CharField(max_length=30, blank=True, help_text='member, excel, manual …')
    event_name = models.CharField(max_length=255, blank=True)
    date_text = models.CharField(max_length=100, blank=True)
    batch = models.UUIDField(null=True, blank=True, db_index=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    pdf = models.FileField(upload_to='certificates/pdf/', blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.number} — {self.recipient_name}'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = CertificateSequence.next_number()
        if not self.event_name:
            self.event_name = self.template.event_name
        if not self.date_text:
            self.date_text = self.template.date_text
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return self.status == self.ACTIVE
