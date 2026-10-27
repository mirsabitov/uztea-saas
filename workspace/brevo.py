"""Brevo email: configuration status only. Sending itself uses Django's SMTP backend,
which root/settings.py points at Brevo's relay when BREVO_SMTP_LOGIN / BREVO_SMTP_KEY are set."""
from django.conf import settings


def is_configured():
    return bool(getattr(settings, 'BREVO_SMTP_LOGIN', '') and getattr(settings, 'BREVO_SMTP_KEY', ''))
