"""certificates.uztea.uz — find, verify and download certificates (no login).

Privacy: looking up by email or membership ID never shows anything on screen; the
links go to the email address on file. Verification by certificate number is public.
"""
import logging
import re

from django.core.cache import cache
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect

from workspace.i18n import LANGUAGES, language_for

from .emails import send_lookup_email
from .models import Certificate
from .render import certificate_pdf

logger = logging.getLogger(__name__)
ID_RE = re.compile(r'^\s*(?:UZ)?0*(\d{1,9})\s*$', re.IGNORECASE)
NUMBER_RE = re.compile(r'^[A-Z]{2,10}-\d{4}-\d{3,8}$')
LOOKUPS_PER_HOUR = 10


def _ctx(request, **extra):
    from workspace.models import OrganizationSettings
    return {'lang': language_for(request), 'languages': LANGUAGES, 'org': OrganizationSettings.get(), **extra}


def _client_ip(request):
    return (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', ''))


def _rate_limited(request):
    key = f'cert-lookup:{_client_ip(request)}'
    try:
        count = cache.get(key, 0)
        if count >= LOOKUPS_PER_HOUR:
            return True
        cache.set(key, count + 1, 3600)
    except Exception:  # cache unavailable: do not block people
        pass
    return False


def _find(query):
    """(email to send to, certificates) for an email address or a membership ID."""
    from app.models import Membership

    query = (query or '').strip()
    match = ID_RE.match(query)
    if match and '@' not in query:
        member = Membership.objects.filter(pk=int(match.group(1))).first()
        if not member or not member.email:
            return None, []
        certs = Certificate.objects.filter(Q(membership=member) | Q(email__iexact=member.email))
        return member.email, list(certs.filter(status=Certificate.ACTIVE).distinct())
    if '@' in query:
        certs = Certificate.objects.filter(email__iexact=query, status=Certificate.ACTIVE)
        return query, list(certs)
    return None, []


@csrf_protect
def home(request):
    number = (request.GET.get('number') or '').strip().upper()
    if number:
        return redirect('certs:verify', number=number)
    sent = False
    error = ''
    if request.method == 'POST':
        query = request.POST.get('query', '')
        if _rate_limited(request):
            error = 'Too many requests. Please try again in an hour.'
        elif not query.strip():
            error = 'Enter your email or membership ID.'
        else:
            email, certs = _find(query)
            if email and certs:
                try:
                    send_lookup_email(email, certs, language_for(request))
                except Exception as exc:
                    logger.warning('Certificate lookup email failed: %s', exc)
            sent = True  # same answer whether or not anything was found
    return render(request, 'certificates/public/home.html', _ctx(request, sent=sent, error=error))


def verify(request, number):
    number = (number or '').strip().upper()
    cert = None
    if NUMBER_RE.match(number):
        cert = Certificate.objects.select_related('template').filter(number=number).first()
    return render(request, 'certificates/public/verify.html', _ctx(request, number=number, cert=cert),
                  status=200 if cert else 404)


def download(request, token):
    try:
        cert = get_object_or_404(Certificate.objects.select_related('template'), token=token)
    except Exception:
        raise Http404
    if not cert.is_valid:
        return render(request, 'certificates/public/verify.html', _ctx(request, number=cert.number, cert=cert), status=410)
    response = HttpResponse(certificate_pdf(cert), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{cert.number}.pdf"'
    return response


def verify_link(number):
    return reverse('certs:verify', args=[number])
