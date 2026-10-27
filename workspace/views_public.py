"""Views that anyone may use (no login): language switch."""
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .i18n import set_language


@require_POST
def change_language(request):
    set_language(request, request.POST.get('language', ''))
    target = request.POST.get('next') or '/'
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = '/'
    return redirect(target)
