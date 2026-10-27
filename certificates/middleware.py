"""Serve the certificate portal at the root of certificates.uztea.uz.

On that host, /v/UZTEA-2026-000001/ is handled as /certificates/v/UZTEA-2026-000001/.
Every other host is untouched. The host must be in ALLOWED_HOSTS on the server.
"""

PASS_THROUGH = ('/certificates/', '/static/', '/media/', '/set-language/')


class CertificatesHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get('HTTP_HOST', '').split(':')[0].lower()
        if host.startswith('certificates.') and not request.path_info.startswith(PASS_THROUGH):
            request.path_info = '/certificates' + request.path_info
        return self.get_response(request)
