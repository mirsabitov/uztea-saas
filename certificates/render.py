"""Turn a certificate template + values into HTML and PDF (headless Chromium, like the membership card)."""
import base64
import logging
import mimetypes
import os

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.template.loader import render_to_string
from django.utils.html import escape
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)

# A4 at 96 dpi
PAGE_SIZES = {'landscape': (1123, 794), 'portrait': (794, 1123)}
FONTS = {'serif': "'Playfair Display', Georgia, 'Times New Roman', serif",
         'sans': "Inter, 'Segoe UI', Arial, sans-serif"}


def verify_base_url():
    return os.getenv('CERTIFICATES_BASE_URL', 'https://certificates.uztea.uz').rstrip('/')


def _data_uri_from_path(path):
    if not path or not os.path.exists(path):
        return ''
    mime = mimetypes.guess_type(path)[0] or 'image/png'
    with open(path, 'rb') as fh:
        return f'data:{mime};base64,{base64.b64encode(fh.read()).decode()}'


def _field_uri(field):
    if not field:
        return ''
    try:
        return _data_uri_from_path(field.path)
    except (ValueError, NotImplementedError):
        return ''


def _organisation_logo():
    try:
        from workspace.models import OrganizationSettings
        return _field_uri(OrganizationSettings.get().logo_light)
    except Exception:
        return ''


def image_sources(template):
    return {
        'uztea_logo': _organisation_logo() or _data_uri_from_path(finders.find('workspace/img/logo-navy.png')),
        'partner_logo': _field_uri(template.partner_logo),
        'extra_logo': _field_uri(template.extra_logo),
        'signature': _field_uri(template.signature),
        'stamp': _field_uri(template.stamp),
    }


def values_for(template, certificate=None, sample_name='Aziza Karimova'):
    number = certificate.number if certificate else 'UZTEA-0000-000000'
    membership = certificate.membership if certificate else None
    return {
        '{name}': certificate.recipient_name if certificate else sample_name,
        '{event}': (certificate.event_name if certificate else '') or template.event_name,
        '{date}': (certificate.date_text if certificate else '') or template.date_text,
        '{number}': number,
        '{membership_id}': f'UZ{membership.pk:06d}' if membership else '',
        '{signer_name}': template.signer_name,
        '{signer_title}': template.signer_title,
        '{verify_url}': f'{verify_base_url().split("://", 1)[-1]}/v/{number}',
    }


def fill(text, values):
    out = escape(text or '')
    for key, value in values.items():
        out = out.replace(escape(key), escape(value or ''))
    return mark_safe(out.replace('\n', '<br>'))


def build_elements(template, values, images, width):
    elements = []
    for el in template.design or []:
        style = (f"left:{float(el.get('x', 50))}%;top:{float(el.get('y', 50))}%;"
                 f"width:{float(el.get('w', 30))}%;")
        if el.get('type') == 'image':
            src = images.get(el.get('source'), '')
            if not src:
                continue  # nothing uploaded for this slot
            elements.append({'type': 'image', 'style': style, 'src': src, 'id': el.get('id')})
        else:
            size = float(el.get('size', 1.5)) * width / 100
            style += (f"font-size:{size:.2f}px;font-weight:{int(el.get('weight', 400))};"
                      f"color:{el.get('color', '#222e50')};text-align:{el.get('align', 'center')};"
                      f"font-family:{FONTS.get(el.get('font'), FONTS['sans'])};"
                      f"letter-spacing:{float(el.get('spacing', 0))}em;")
            elements.append({'type': 'text', 'style': style, 'html': fill(el.get('text', ''), values),
                             'line': bool(el.get('line')), 'id': el.get('id')})
    return elements


def render_html(template, certificate=None, sample_name='Aziza Karimova'):
    width, height = PAGE_SIZES.get(template.orientation, PAGE_SIZES['landscape'])
    values = values_for(template, certificate, sample_name)
    images = image_sources(template)
    return render_to_string('certificates/render.html', {
        't': template, 'width': width, 'height': height,
        'background': _field_uri(template.background),
        'elements': build_elements(template, values, images, width),
    })


def html_to_pdf(htmls, orientation='landscape'):
    """Render one or more HTML pages to PDF bytes, reusing one browser."""
    from playwright.sync_api import sync_playwright

    width, height = PAGE_SIZES.get(orientation, PAGE_SIZES['landscape'])
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        try:
            page = browser.new_page(viewport={'width': width, 'height': height})
            for html in htmls:
                page.set_content(html, wait_until='networkidle')
                try:
                    page.evaluate('document.fonts && document.fonts.ready')
                except Exception:
                    pass
                out.append(page.pdf(width=f'{width}px', height=f'{height}px', print_background=True,
                                    margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'}))
        finally:
            browser.close()
    return out


def _pdf_is_current(certificate):
    if not certificate.pdf:
        return False
    try:
        rendered = default_storage.get_modified_time(certificate.pdf.name)
        return default_storage.exists(certificate.pdf.name) and rendered >= certificate.template.updated_at
    except Exception:
        return False


def certificate_pdf(certificate):
    """PDF bytes for one certificate; cached in media until its template changes."""
    if _pdf_is_current(certificate):
        with certificate.pdf.open('rb') as fh:
            return fh.read()
    pdf = html_to_pdf([render_html(certificate.template, certificate)], certificate.template.orientation)[0]
    if certificate.pdf:
        certificate.pdf.delete(save=False)
    certificate.pdf.save(f'{certificate.number}.pdf', ContentFile(pdf), save=True)
    return pdf


def certificates_zip(certificates):
    """ZIP of many certificates (one browser session)."""
    import io
    import zipfile

    certificates = list(certificates)
    pending = [c for c in certificates if not _pdf_is_current(c)]
    if pending:
        by_orientation = {}
        for c in pending:
            by_orientation.setdefault(c.template.orientation, []).append(c)
        for orientation, group in by_orientation.items():
            pdfs = html_to_pdf([render_html(c.template, c) for c in group], orientation)
            for c, pdf in zip(group, pdfs):
                if c.pdf:
                    c.pdf.delete(save=False)
                c.pdf.save(f'{c.number}.pdf', ContentFile(pdf), save=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for c in certificates:
            with c.pdf.open('rb') as fh:
                zf.writestr(f'{c.number} {c.recipient_name}.pdf'.replace('/', '-'), fh.read())
    return buffer.getvalue()


def media_ok():
    return bool(getattr(settings, 'MEDIA_ROOT', None))
