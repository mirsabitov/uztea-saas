"""Certificates inside the workspace: templates & designer, issuing, the issued list."""
import json
import uuid

from django import forms
from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from workspace.access import can, render_ws, workspace_view
from workspace.views import PAGE_SIZES, _page, _query_without

from . import recipients as rcp
from .emails import download_url, send_certificate_emails
from .models import IMAGE_SOURCES, PLACEHOLDERS, Certificate, CertificateTemplate, default_design
from .render import certificate_pdf, certificates_zip, html_to_pdf, render_html

SECTION = 'certificates'
IMAGE_FIELDS = ['background', 'partner_logo', 'extra_logo', 'signature', 'stamp']
MAX_IMAGE = 4 * 1024 * 1024


class TemplateForm(forms.ModelForm):
    class Meta:
        model = CertificateTemplate
        fields = ['name', 'event_name', 'date_text', 'event', 'signer_name', 'signer_title', 'orientation',
                  'accent_color', 'frame', 'is_active']
        widgets = {'accent_color': forms.TextInput(attrs={'type': 'color'})}


def _clean_design(raw):
    """Keep only known keys and sane values from the designer's JSON."""
    try:
        items = json.loads(raw or '[]')
    except ValueError:
        return None
    if not isinstance(items, list):
        return None
    clean = []
    sources = {key for key, _ in IMAGE_SOURCES}
    for el in items[:40]:
        if not isinstance(el, dict):
            continue
        num = lambda k, d, lo, hi: max(lo, min(hi, float(el.get(k, d) or d)))
        item = {'id': str(el.get('id', ''))[:40] or uuid.uuid4().hex[:8], 'x': num('x', 50, 0, 100),
                'y': num('y', 50, 0, 100), 'w': num('w', 30, 2, 100)}
        if el.get('type') == 'image' and el.get('source') in sources:
            item.update(type='image', source=el['source'])
        else:
            color = str(el.get('color', '#222e50'))
            item.update(type='text', text=str(el.get('text', ''))[:600], size=num('size', 1.5, 0.4, 12),
                        weight=int(num('weight', 400, 300, 900)), color=color if color.startswith('#') and len(color) <= 7 else '#222e50',
                        align=el.get('align') if el.get('align') in ('left', 'center', 'right') else 'center',
                        font='serif' if el.get('font') == 'serif' else 'sans', spacing=num('spacing', 0, 0, 1),
                        line=bool(el.get('line')))
        clean.append(item)
    return clean


@workspace_view(SECTION, 'certificates.view_certificatetemplate', 'certificates.view_certificate')
def templates_list(request):
    user = request.user
    templates = CertificateTemplate.objects.annotate(issued=Count('certificates')).select_related('event')
    return render_ws(request, 'certificates/workspace/templates.html', {
        'page_title': 'Certificates', 'page_subtitle': 'Design, number, issue and send certificates',
        'cert_tab': 'templates', 'templates': templates,
        'can_add': can(user, 'certificates.add_certificatetemplate'),
        'can_issue': can(user, 'certificates.add_certificate'),
        'can_change': can(user, 'certificates.change_certificatetemplate'),
    }, SECTION)


@workspace_view(SECTION, 'certificates.add_certificatetemplate')
def template_new(request):
    if request.method != 'POST':
        return redirect('workspace:cert_templates')
    template = CertificateTemplate.objects.create(name='New certificate', event_name='UzTEA event',
                                                  created_by=request.user, design=default_design())
    return redirect('workspace:cert_designer', pk=template.pk)


@workspace_view(SECTION, 'certificates.change_certificatetemplate', 'certificates.view_certificatetemplate')
def designer(request, pk):
    template = get_object_or_404(CertificateTemplate, pk=pk)
    can_edit = request.user.has_perm('certificates.change_certificatetemplate')
    form = TemplateForm(request.POST or None, instance=template)
    if request.method == 'POST' and can_edit:
        design = _clean_design(request.POST.get('design'))
        too_big = [f.name for f in request.FILES.values() if f.size > MAX_IMAGE]
        if design is None:
            form.add_error(None, 'The layout could not be read. Reload the page and try again.')
        elif too_big:
            form.add_error(None, f"Images over 4 MB: {', '.join(too_big)}")
        elif form.is_valid():
            obj = form.save(commit=False)
            obj.design = design
            for field in IMAGE_FIELDS:
                if request.POST.get(f'clear_{field}'):
                    getattr(obj, field).delete(save=False)
                    setattr(obj, field, '')
                if field in request.FILES:
                    setattr(obj, field, request.FILES[field])
            obj.save()
            messages.success(request, f'Saved "{obj}".')
            return redirect('workspace:cert_designer', pk=obj.pk)
    from workspace.models import OrganizationSettings
    images = {'uztea_logo': OrganizationSettings.get().logo_urls()['light']}
    for field in IMAGE_FIELDS:
        f = getattr(template, field)
        images[field] = f.url if f else ''
    return render_ws(request, 'certificates/workspace/designer.html', {
        'page_title': 'Certificate designer', 'template': template, 'form': form, 'can_edit': can_edit,
        'design_data': template.design, 'images': images,
        'image_sources': IMAGE_SOURCES, 'placeholders': PLACEHOLDERS,
        'image_fields': [(f, dict(IMAGE_SOURCES).get(f, 'Background'), getattr(template, f)) for f in IMAGE_FIELDS],
        'sample': {'{name}': 'Aziza Karimova', '{event}': template.event_name, '{date}': template.date_text,
                   '{number}': 'UZTEA-2026-000123', '{membership_id}': 'UZ000090',
                   '{signer_name}': template.signer_name, '{signer_title}': template.signer_title,
                   '{verify_url}': 'certificates.uztea.uz/v/UZTEA-2026-000123'},
    }, SECTION)


@workspace_view(SECTION, 'certificates.view_certificatetemplate')
def template_preview(request, pk):
    template = get_object_or_404(CertificateTemplate, pk=pk)
    pdf = html_to_pdf([render_html(template)], template.orientation)[0]
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="preview-{template.pk}.pdf"'
    return response


@workspace_view(SECTION, 'certificates.add_certificate')
def issue(request):
    templates = CertificateTemplate.objects.filter(is_active=True)
    step = request.POST.get('step', '')
    template_id = request.POST.get('template') or request.GET.get('template')
    template = templates.filter(pk=template_id).first() if template_id and str(template_id).isdigit() else None
    rows, problems = [], []

    if request.method == 'POST' and step == 'issue':
        try:
            rows = json.loads(request.POST.get('rows') or '[]')
        except ValueError:
            rows = []
        rows, problems = rcp.normalise(rows)
        if not template:
            messages.error(request, 'Choose a certificate template.')
        elif not rows:
            messages.error(request, 'There is nobody to issue certificates to.')
        else:
            skip_existing = bool(request.POST.get('skip_existing'))
            existing = set()
            if skip_existing:
                existing = {e.lower() for e in Certificate.objects.filter(template=template).exclude(email='')
                            .values_list('email', flat=True)}
                existing |= {f'm{m}' for m in Certificate.objects.filter(template=template, membership__isnull=False)
                             .values_list('membership_id', flat=True)}
            batch = uuid.uuid4()
            created = []
            for row in rows:
                if skip_existing and ((row['email'] and row['email'] in existing)
                                      or (row['membership_id'] and f"m{row['membership_id']}" in existing)):
                    continue
                created.append(Certificate.objects.create(
                    template=template, recipient_name=row['name'], email=row['email'],
                    membership_id=row['membership_id'], source=request.POST.get('source', 'manual')[:30],
                    batch=batch, created_by=request.user))
            note = f'Issued {len(created)} certificate(s)'
            if len(created) < len(rows):
                note += f'; {len(rows) - len(created)} skipped (already had one)'
            if created and request.POST.get('send_email'):
                sent, skipped, failed = send_certificate_emails(created, request.user)
                note += f'; emailed {sent}' + (f', {skipped} without email' if skipped else '') + (f', {failed} failed' if failed else '')
            messages.success(request, note + '.')
            return redirect(reverse('workspace:cert_issued') + f'?batch={batch}')

    source = request.POST.get('source') or request.GET.get('source') or ''
    if request.method == 'POST' and step == 'load':
        if request.FILES.get('file'):
            try:
                rows = rcp.parse_upload(request.FILES['file'])
                source = 'excel'
            except Exception as exc:
                messages.error(request, f'Could not read the file: {exc}')
        elif request.POST.get('paste', '').strip():
            rows = rcp.parse_paste(request.POST['paste'])
            source = 'manual'
        rows, problems = rcp.normalise(rows)
    elif source == 'member':
        from workspace.messaging import parse_ids
        ids = parse_ids(request.POST.getlist('_selected_action') or request.GET.getlist('ids'))
        rows = rcp.from_members(ids)

    return render_ws(request, 'certificates/workspace/issue.html', {
        'page_title': 'Issue certificates', 'cert_tab': 'issue', 'templates': templates, 'template': template,
        'rows': rows, 'rows_json': json.dumps(rows), 'problems': problems, 'source': source,
        'with_email': sum(1 for r in rows if r['email']), 'linked': sum(1 for r in rows if r['membership_id']),
        'max_rows': rcp.MAX_ROWS,
    }, SECTION)


@workspace_view(SECTION, 'certificates.view_certificate')
def issued(request):
    qs = Certificate.objects.select_related('template', 'membership')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(recipient_name__icontains=q) | Q(email__icontains=q)
                       | Q(event_name__icontains=q))
    for key in ('template', 'status', 'batch'):
        value = request.GET.get(key)
        if value:
            try:
                qs = qs.filter(**{key: value})
            except Exception:
                qs = qs.none()
    page, per_page = _page(request, qs)
    user = request.user
    return render_ws(request, 'certificates/workspace/issued.html', {
        'page_title': 'Certificates', 'page_subtitle': 'Every certificate has a unique number',
        'cert_tab': 'issued', 'page': page, 'per_page': per_page, 'page_sizes': PAGE_SIZES,
        'total': page.paginator.count, 'q': q, 'filters': request.GET, 'batch': request.GET.get('batch', ''),
        'templates': CertificateTemplate.objects.all(), 'status_options': Certificate.STATUS_CHOICES,
        'base_query': _query_without(request, 'page'),
        'can_change': can(user, 'certificates.change_certificate'),
        'rows': [{'c': c, 'url': download_url(c)} for c in page.object_list],
    }, SECTION)


@workspace_view(SECTION, 'certificates.view_certificate')
def download(request, pk):
    cert = get_object_or_404(Certificate.objects.select_related('template'), pk=pk)
    response = HttpResponse(certificate_pdf(cert), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{cert.number}.pdf"'
    return response


@workspace_view(SECTION, 'certificates.view_certificate')
def download_batch(request):
    batch = request.GET.get('batch', '')
    try:
        certs = list(Certificate.objects.select_related('template').filter(batch=batch)[:300])
    except Exception:
        certs = []
    if not certs:
        messages.warning(request, 'Nothing to download for this batch.')
        return redirect('workspace:cert_issued')
    response = HttpResponse(certificates_zip(certs), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="certificates.zip"'
    return response


@workspace_view(SECTION, 'certificates.change_certificate')
def certificate_action(request, pk):
    cert = get_object_or_404(Certificate, pk=pk)
    back = request.POST.get('next') or ''
    if not back.startswith('/') or back.startswith('//'):
        back = reverse('workspace:cert_issued')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'revoke':
            cert.status = Certificate.REVOKED
            cert.save(update_fields=['status'])
            messages.success(request, f'{cert.number} revoked. Its link and verification now show it as revoked.')
        elif action == 'restore':
            cert.status = Certificate.ACTIVE
            cert.save(update_fields=['status'])
            messages.success(request, f'{cert.number} is valid again.')
        elif action == 'email':
            sent, skipped, failed = send_certificate_emails([cert], request.user)
            if sent:
                messages.success(request, f'Emailed {cert.number} to {cert.email}.')
            else:
                messages.error(request, 'Not sent: ' + ('no email address.' if skipped else 'the email server refused it.'))
    return redirect(back)
