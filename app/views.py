from pathlib import Path
from functools import lru_cache
from io import BytesIO

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.cache import cache_control
from .forms import MembershipForm
from .models import Membership
from .pricing import get_membership_price
from click.models import Order
from click.utils import build_membership_card_context, get_click_url, get_card_payment_url
from types import SimpleNamespace
from PIL import Image


@lru_cache(maxsize=1)
def get_uztea_email_logo_bytes():
    """Build a transparent white email logo from the existing admin logo."""
    source_path = settings.BASE_DIR / 'static' / 'images' / 'logo.png'
    if not source_path.exists():
        raise FileNotFoundError('Admin logo not found')

    source = Image.open(source_path).convert('RGBA')
    source = source.resize((432, 308), Image.Resampling.LANCZOS)
    white_logo = Image.new('RGBA', source.size, (255, 255, 255, 0))
    white_logo.putalpha(source.getchannel('A'))
    output = BytesIO()
    white_logo.save(output, format='PNG', optimize=True)
    return output.getvalue()


@cache_control(public=True, max_age=86400)
def matchedexpo_email_header(request):
    image_path = settings.BASE_DIR / 'static' / 'images' / 'matchedexpo-email-header.png'
    if not image_path.exists():
        raise Http404('MatchED Expo email header not found')
    return FileResponse(image_path.open('rb'), content_type='image/png')


@cache_control(public=True, max_age=86400)
def uztea_email_logo(request):
    return FileResponse(BytesIO(get_uztea_email_logo_bytes()), content_type='image/png')


def _serve_pdf(path, filename):
    static_path = finders.find(path)
    fallback_path = settings.BASE_DIR / 'templates' / filename
    pdf_path = Path(static_path) if static_path else fallback_path

    if not pdf_path.exists():
        raise Http404('Document not found')

    return FileResponse(
        pdf_path.open('rb'),
        content_type='application/pdf',
        as_attachment=False,
        filename=filename,
    )


def membership_terms(request):
    return _serve_pdf(
        'docs/UzTEA_Membership_Terms.pdf',
        'UzTEA_Membership_Terms.pdf',
    )


def privacy_policy(request):
    return _serve_pdf(
        'docs/UzTEA_Privacy_Policy.pdf',
        'UzTEA_Privacy_Policy.pdf',
    )


def auth_login(request):
    return render(request, 'uztea-auth.html')


def membership_create(request):
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        form = MembershipForm(request.POST, request.FILES)
        if form.is_valid():
            if request.POST.get('preview_card') == '1':
                membership = form.save(commit=False)
                amount = get_membership_price(membership.membership_type)
                order = SimpleNamespace(
                    id='demo',
                    pk='demo',
                    status='paid',
                    amount=amount,
                    updated_at=timezone.now(),
                    click_trans_id='DEMO',
                )
                member_url = request.build_absolute_uri(request.path)
                return render(
                    request,
                    'membership-card.html',
                    build_membership_card_context(membership, order, member_url, demo=True),
                )

            membership = form.save()
            amount = get_membership_price(membership.membership_type)
            order = Order.objects.create(
                membership=membership,
                amount=amount,
                user=request.user if request.user.is_authenticated else None
            )

            if is_ajax:
                from payme.views import generate_payme_url
                return JsonResponse({
                    'success': True,
                    'order_id': order.id,
                    'amount': float(order.amount),
                    'amount_tiyin': int(float(order.amount) * 100),
                    'click_url': get_click_url(order.id, order.amount),
                    'card_url': get_card_payment_url(order.id, order.amount),
                    'payme_url': generate_payme_url(order),
                    'atmos_url': f'/payments/atmos/pay/?order={order.id}&amount={int(float(order.amount) * 100)}',
                    'status_url': reverse('payment_status', args=[order.pk]),
                })

            return redirect('payment_status', order_pk=order.pk)

        if is_ajax:
            field_errors = {k: [str(e) for e in v] for k, v in form.errors.items()}
            return JsonResponse({'success': False, 'errors': field_errors}, status=400)
    else:
        form = MembershipForm()

    return render(request, 'membership_form.html', {'form': form})


def success_view(request):
    return render(request, 'success.html')


def membership_card(request, pk):
    """Render the membership card for any membership (used from admin).

    With ?download=1 the card is rendered server-side (headless Chromium)
    and returned as a PNG attachment — direct download, no browser tab UI.
    """
    membership = get_object_or_404(Membership, pk=pk)
    order = membership.orders.order_by('-updated_at').first()
    if order is None:
        order = SimpleNamespace(
            id='-', pk='-', status='paid',
            amount=get_membership_price(membership.membership_type),
            updated_at=membership.created_at or timezone.now(),
            click_trans_id='ADMIN',
        )
    member_url = request.build_absolute_uri(reverse('membership_card', args=[membership.pk]))
    ctx = build_membership_card_context(membership, order, member_url)

    if request.GET.get('download') == '1':
        from django.template.loader import render_to_string
        from django.http import HttpResponse
        try:
            from .card_render import render_card_png
            html = render_to_string('membership-card.html', ctx, request=request)
            png = render_card_png(html, selector='.card')
            resp = HttpResponse(png, content_type='image/png')
            resp['Content-Disposition'] = (
                f'attachment; filename="UzTEA-card-{ctx["card_id"]}.png"'
            )
            return resp
        except Exception:
            # Fall back to the in-browser card with auto-download if rendering fails
            import logging
            logging.getLogger('app').exception('membership_card | png render failed pk=%s', pk)

    return render(request, 'membership-card.html', ctx)


def card_preview(request):
    from types import SimpleNamespace
    from django.utils import timezone
    from datetime import timedelta
    from click.utils import build_membership_card_context

    membership = SimpleNamespace(
        full_name='Webster Mirzobitov',
        phone_number='+998997214262',
        email='mmirsobitov@webster.edu',
        country='Uzbekistan',
        region_city='Tashkent',
        institution_name='Webster University',
        contact_person_name=None,
        contact_person_email=None,
        get_membership_type_display=lambda: 'Basic Membership',
        membership_type='basic',
        id=1,
    )
    order = SimpleNamespace(
        id='demo',
        pk='demo',
        status='paid',
        amount=100000,
        updated_at=timezone.now(),
        click_trans_id='DEMO',
    )
    member_url = request.build_absolute_uri('/apply/')
    ctx = build_membership_card_context(membership, order, member_url, demo=True)
    return render(request, 'membership-card.html', ctx)
