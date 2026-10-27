from datetime import timedelta
import os

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import Http404
from django import forms
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

from app.models import (
    AnniversaryRegistration,
    ConferenceRegistration,
    Membership,
    MembershipTypeConfig,
    Partner,
    TeacherBank,
)
from app import membership_lifecycle as lifecycle
from app.payment_status import membership_payment_status
from atmos.models import AtmosTransaction
from click.models import Order, PromoCode
from payme.models import PaymeTransaction

from . import dashboard, messaging, people
from .access import admin_url, can, render_ws, workspace_view
from .studio import FIELD_LIBRARY, SMART_BLOCKS, TEMPLATES as FORM_TEMPLATES

PAGE_SIZES = (25, 50, 100)


def _page(request, items, default=25):
    try:
        size = int(request.GET.get('per_page', default))
    except ValueError:
        size = default
    if size not in PAGE_SIZES:
        size = default
    page = Paginator(items, size).get_page(request.GET.get('page'))
    return page, size


def _query_without(request, *keys):
    params = request.GET.copy()
    for key in keys:
        params.pop(key, None)
    return params.urlencode()


def _message_url(user, source):
    """Compose URL for the SMS / Email buttons, or None when the user may not send to this list."""
    if not messaging.can_send(user, source):
        return None
    return reverse('workspace:message_compose') + f'?source={source}'


def _bulk_action(user, changelist, actions, perm):
    """Bulk actions are posted to the existing admin changelist, which runs them."""
    url = admin_url(changelist)
    if not url or not can(user, perm):
        return None
    return {'url': url, 'actions': actions}


# ── Home ────────────────────────────────────────────────────────────────────

@workspace_view('home')
def home(request):
    user = request.user
    activity = []
    if can(user, 'app.view_membership'):
        for m in Membership.objects.order_by('-created_at')[:6]:
            activity.append({'when': m.created_at, 'icon': 'id-card', 'tone': 'blue',
                             'title': m.full_name, 'text': f'Membership application · {m.get_membership_type_display()}',
                             'url': reverse('workspace:people') + f'?preview={m.pk}'
                             + ('&view=pending' if m.is_pending_payment else '')})
    if can(user, 'app.view_conferenceregistration'):
        for r in ConferenceRegistration.objects.order_by('-created_at')[:4]:
            activity.append({'when': r.created_at, 'icon': 'calendar', 'tone': 'orange',
                             'title': r.full_name, 'text': 'TESOL Conference registration',
                             'url': admin_url('app_conferenceregistration_change', r.pk)})
    if can(user, 'app.view_anniversaryregistration'):
        for r in AnniversaryRegistration.objects.order_by('-created_at')[:4]:
            activity.append({'when': r.created_at, 'icon': 'calendar', 'tone': 'orange',
                             'title': r.full_name, 'text': '30th Anniversary registration',
                             'url': admin_url('app_anniversaryregistration_change', r.pk)})
    if can(user, 'click.view_order'):
        for o in Order.objects.filter(status='paid').select_related('membership', 'conference_registration').order_by('-updated_at')[:4]:
            who = o.membership or o.conference_registration
            activity.append({'when': o.updated_at, 'icon': 'credit-card', 'tone': 'green',
                             'title': f'Order #{o.pk} paid',
                             'text': f'{who} · {o.amount:,.0f} UZS'.replace(',', ' ') if who else f'{o.amount:,.0f} UZS',
                             'url': admin_url('click_order_change', o.pk)})
    activity.sort(key=lambda e: e['when'], reverse=True)

    attention = []
    dash = dashboard.build(user, request.GET.get('period'))
    counts = dash.get('lifecycle_counts') or {}
    if counts.get(lifecycle.RENEWAL_DUE):
        attention.append({'count': counts[lifecycle.RENEWAL_DUE], 'label': 'memberships end within 30 days (renewal due)',
                          'url': reverse('workspace:people') + '?status=renewal_due&sort=renewal'})
    if can(user, 'app.view_pendingpayment'):
        n = Membership.objects.filter(is_pending_payment=True).count()
        if n:
            attention.append({'count': n, 'label': 'applications in the Pending Payment list',
                              'url': reverse('workspace:people') + '?view=pending'})
    if can(user, 'click.view_order'):
        n = Order.objects.filter(status__in=('pending', 'processing')).count()
        if n:
            attention.append({'count': n, 'label': 'orders not paid yet (pending or processing)',
                              'url': reverse('workspace:payments') + '?tab=orders&status=pending'})
    if can(user, 'atmos.view_atmostransaction'):
        n = AtmosTransaction.objects.filter(status='FAILED', created_at__gte=timezone.now() - timedelta(days=7)).count()
        if n:
            attention.append({'count': n, 'label': 'failed Atmos transactions in the last 7 days',
                              'url': reverse('workspace:payments') + '?tab=atmos&status=FAILED'})

    return render_ws(request, 'workspace/home.html', {
        'page_title': 'Home',
        'activity': activity[:10],
        'attention': attention,
        'add_person_url': admin_url('app_membership_add') if can(user, 'app.add_membership') else None,
        'legacy_events': _legacy_forms(user, kinds=('event',)),
        'dash': dash,
        'can_view_members': can(user, 'app.view_membership', 'app.view_pendingpayment'),
        'can_view_orders': can(user, 'click.view_order'),
    }, 'home')


# ── People ──────────────────────────────────────────────────────────────────

MEMBER_ACTIONS = [
    ('compose_custom_email', 'Send custom email'),
    ('resend_welcome_email', 'Resend welcome email'),
    ('move_to_pending_payment', 'Move non-success payments to Pending Payment'),
]
PENDING_ACTIONS = [
    ('compose_custom_email', 'Send custom email'),
    ('return_to_memberships', 'Return to Members'),
]
CONTACT_EMAIL_ACTIONS = [('compose_custom_email', 'Send custom email')]


@workspace_view('people', 'app.view_membership', 'app.view_pendingpayment')
def people_members(request):
    user = request.user
    view = request.GET.get('view', 'all')
    if view not in ('all', 'pending'):
        view = 'all'
    # The two lists mirror the admin: Memberships and Pending Payments.
    if view == 'all' and not can(user, 'app.view_membership'):
        view = 'pending'
    if view == 'pending' and not can(user, 'app.view_pendingpayment'):
        view = 'all'
    pending = view == 'pending'

    qs, sort = people.filter_members(request.GET, pending)
    page, per_page = _page(request, qs)
    type_options = people.membership_type_options()
    rows = people.member_rows(list(page.object_list), dict(type_options))

    opt = 'app_pendingpayment' if pending else 'app_membership'
    preview = None
    preview_pk = request.GET.get('preview')
    if preview_pk and preview_pk.isdigit():
        member = Membership.objects.filter(pk=int(preview_pk)).first()
        if member is not None:
            preview = _preview_context(request, member)

    countries = (Membership.objects.filter(is_pending_payment=pending).exclude(country='')
                 .order_by('country').values_list('country', flat=True).distinct())
    active_filters = [k for k in ('type', 'position', 'language', 'institution_type', 'country', 'status') if request.GET.get(k)]

    return render_ws(request, 'workspace/people/members.html', {
        'page_title': 'People',
        'page_subtitle': 'Your members and professional community',
        'people_tab': 'members',
        'view': view,
        'can_all': can(user, 'app.view_membership'),
        'can_pending': can(user, 'app.view_pendingpayment'),
        'can_teachers_bank': can(user, 'app.view_teacherbank'),
        'page': page,
        'per_page': per_page,
        'page_sizes': PAGE_SIZES,
        'rows': rows,
        'total': page.paginator.count,
        'sort': sort,
        'q': request.GET.get('q', ''),
        'filters': request.GET,
        'active_filter_count': len(active_filters),
        'type_options': type_options,
        'position_options': Membership.POSITION_CHOICES,
        'language_options': Membership.LANGUAGE_CHOICES,
        'institution_type_options': Membership.INSTITUTION_TYPE_CHOICES,
        'status_options': people.STATUS_FILTER_LABELS,
        'status': request.GET.get('status', ''),
        'country_options': countries,
        'base_query': _query_without(request, 'page', 'preview'),
        'sort_query': _query_without(request, 'sort', 'page', 'preview'),
        'filter_query': _query_without(request, 'preview'),
        'import_url': admin_url(f'{opt}_import') if can(user, 'app.add_membership') else None,
        'export_url': admin_url(f'{opt}_export') if can(user, 'app.view_membership') else None,
        'add_url': admin_url('app_membership_add') if can(user, 'app.add_membership') else None,
        'bulk': _bulk_action(
            user, f'{opt}_changelist',
            PENDING_ACTIONS if pending else MEMBER_ACTIONS,
            'app.change_pendingpayment' if pending else 'app.change_membership',
        ),
        'preview': preview,
        'message_url': _message_url(user, 'member'),
        'cert_issue_url': (reverse('workspace:cert_issue') + '?source=member')
        if can(user, 'certificates.add_certificate') else None,
    }, 'people')


def _member_or_404(request, pk):
    member = get_object_or_404(Membership, pk=pk)
    perm = 'app.view_pendingpayment' if member.is_pending_payment else 'app.view_membership'
    if not can(request.user, perm):
        raise Http404
    return member


def _preview_context(request, member):
    user = request.user
    opt = 'app_pendingpayment' if member.is_pending_payment else 'app_membership'
    payment = people.payment_badge(membership_payment_status(member))
    member_status = lifecycle.membership_status(member)
    perm_view = 'app.view_pendingpayment' if member.is_pending_payment else 'app.view_membership'
    if not can(user, perm_view):
        return None
    return {
        'member': member,
        'membership_id': people.membership_id(member.pk),
        'initials': people.initials(member.full_name),
        'payment': payment,
        'status': member_status,
        'is_demo': people.is_demo_email(member.email),
        'activity': people.membership_activity(member)[:5],
        'profile_url': reverse('workspace:member_profile', args=[member.pk]),
        'edit_url': admin_url(f'{opt}_change', member.pk)
        if can(user, 'app.change_membership', 'app.change_pendingpayment') else None,
        'card_url': reverse('membership_card', args=[member.pk]) + '?download=1',
        'message_url': (_message_url(user, 'member') + f'&ids={member.pk}') if _message_url(user, 'member') else None,
    }


@workspace_view('people', 'app.view_membership', 'app.view_pendingpayment')
def member_preview(request, pk):
    member = _member_or_404(request, pk)
    return render_ws(request, 'workspace/people/_preview.html',
                     {'preview': _preview_context(request, member)}, 'people')


@workspace_view('people', 'app.view_membership', 'app.view_pendingpayment')
def member_profile(request, pk):
    member = _member_or_404(request, pk)
    user = request.user
    ctx = _preview_context(request, member)
    orders = []
    if can(user, 'click.view_order'):
        order_list = list(member.orders.select_related('promocode').prefetch_related('payme_transactions').order_by('-created_at'))
        atmos = {}
        for txn in AtmosTransaction.objects.filter(account__in=[str(o.pk) for o in order_list]).order_by('-created_at'):
            atmos.setdefault(txn.account, []).append(txn)
        for o in order_list:
            orders.append({'order': o, 'atmos': atmos.get(str(o.pk), []),
                           'payme': list(o.payme_transactions.all()),
                           'url': admin_url('click_order_change', o.pk)})
    ctx.update({
        'page_title': member.full_name,
        'sections': people.profile_sections(member),
        'orders': orders,
        'can_view_orders': can(user, 'click.view_order'),
        'related': people.related_by_email(user, member.email, exclude_membership=member),
        'all_activity': people.membership_activity(member),
        'list_name': 'Pending Payment list' if member.is_pending_payment else 'Members list',
        'list_url': reverse('workspace:people') + ('?view=pending' if member.is_pending_payment else ''),
        'payment_proof_url': member.payment_proof.url if member.payment_proof else None,
        'institution_members': people.institution_members(member),
    })
    return render_ws(request, 'workspace/people/profile.html', ctx, 'people')


@workspace_view('people', 'app.view_teacherbank')
def people_teachers_bank(request):
    user = request.user
    qs = TeacherBank.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q)
                       | Q(phone_number__icontains=q) | Q(source__icontains=q))
    source = request.GET.get('source', '')
    if source:
        qs = qs.filter(source=source)
    page, per_page = _page(request, qs.order_by('full_name', 'id'))
    sources = (TeacherBank.objects.exclude(source__isnull=True).exclude(source='')
               .order_by('source').values_list('source', flat=True).distinct())
    rows = [{'obj': t, 'initials': people.initials(t.full_name or t.email or '?'),
             'is_demo': people.is_demo_email(t.email),
             'url': admin_url('app_teacherbank_change', t.pk)} for t in page.object_list]
    return render_ws(request, 'workspace/people/teachers_bank.html', {
        'page_title': 'People',
        'page_subtitle': 'Your members and professional community',
        'people_tab': 'teachers_bank',
        'can_all': can(user, 'app.view_membership'),
        'can_pending': can(user, 'app.view_pendingpayment'),
        'can_teachers_bank': True,
        'page': page, 'per_page': per_page, 'page_sizes': PAGE_SIZES,
        'rows': rows, 'total': page.paginator.count, 'q': q, 'source': source, 'sources': sources,
        'base_query': _query_without(request, 'page'),
        'import_url': admin_url('app_teacherbank_import') if can(user, 'app.add_teacherbank') else None,
        'export_url': admin_url('app_teacherbank_export'),
        'add_url': admin_url('app_teacherbank_add') if can(user, 'app.add_teacherbank') else None,
        'bulk': _bulk_action(user, 'app_teacherbank_changelist', CONTACT_EMAIL_ACTIONS, 'app.change_teacherbank'),
        'message_url': _message_url(user, 'teachers_bank'),
    }, 'people')


@workspace_view('people')
def people_contacts(request):
    user = request.user
    q = request.GET.get('q', '')
    source = request.GET.get('source', '')
    rows = people.all_contacts(user, q, source)
    page, per_page = _page(request, rows, default=50)
    return render_ws(request, 'workspace/people/contacts.html', {
        'page_title': 'People',
        'page_subtitle': 'Your members and professional community',
        'people_tab': 'contacts',
        'can_all': can(user, 'app.view_membership'),
        'can_pending': can(user, 'app.view_pendingpayment'),
        'can_teachers_bank': can(user, 'app.view_teacherbank'),
        'page': page, 'per_page': per_page, 'page_sizes': PAGE_SIZES,
        'total': page.paginator.count, 'q': q, 'source': source,
        'sources': [(s[0], s[1]) for s in people.contact_sources_for(user)]
        + ([people.INSTITUTION_MEMBER_SOURCE] if can(user, 'app.view_membership') else []),
        'base_query': _query_without(request, 'page'),
    }, 'people')


# ── Forms & Events ──────────────────────────────────────────────────────────

def _legacy_forms(user, kinds=('membership', 'event')):
    """The three existing public forms, with real response counts."""
    forms = []
    specs = [
        ('membership', 'Membership application', 'Join UzTEA and become a member', 'membership_form',
         'app.view_membership', Membership, 'app_membership', 'id-card', 'Membership'),
        ('event', 'TESOL Conference registration', 'Conference registration with online payment',
         'conference_register', 'app.view_conferenceregistration', ConferenceRegistration,
         'app_conferenceregistration', 'calendar', 'Event'),
        ('event', '30th Anniversary registration', 'UzTEA 30 years celebration registration',
         'anniversary_register', 'app.view_anniversaryregistration', AnniversaryRegistration,
         'app_anniversaryregistration', 'calendar', 'Event'),
    ]
    for kind, title, subtitle, url_name, perm, model, opt, icon, kind_label in specs:
        if kind not in kinds or not can(user, perm):
            continue
        stats = model.objects.aggregate(n=Count('id'), last=Max('created_at'))
        forms.append({
            'kind': kind, 'kind_label': kind_label, 'title': title, 'subtitle': subtitle, 'icon': icon,
            'public_url': reverse(url_name), 'responses': stats['n'], 'last_response': stats['last'],
            'responses_url': admin_url(f'{opt}_changelist'),
            'export_url': admin_url(f'{opt}_export'),
        })
    return forms


@workspace_view('forms')
def forms_list(request):
    tab = request.GET.get('tab', 'all')
    if tab not in ('all', 'published', 'drafts', 'archived'):
        tab = 'all'
    q = request.GET.get('q', '').strip().lower()
    forms = _legacy_forms(request.user) if tab in ('all', 'published') else []
    if q:
        forms = [f for f in forms if q in f['title'].lower() or q in f['subtitle'].lower()]
    return render_ws(request, 'workspace/forms/list.html', {
        'page_title': 'Forms & Events',
        'page_subtitle': 'Build forms. Run events. Grow your community.',
        'tab': tab, 'q': request.GET.get('q', ''), 'forms': forms,
        'templates': FORM_TEMPLATES,
    }, 'forms')


@workspace_view('forms')
def form_studio(request):
    key = request.GET.get('template', 'event')
    template = next((t for t in FORM_TEMPLATES if t['key'] == key), FORM_TEMPLATES[0])
    return render_ws(request, 'workspace/forms/studio.html', {
        'page_title': 'Form Studio',
        'template': template,
        'field_library': FIELD_LIBRARY,
        'smart_blocks': SMART_BLOCKS,
        'templates': FORM_TEMPLATES,
    }, 'forms')


# ── Payments ────────────────────────────────────────────────────────────────

PAYMENT_TABS = [
    ('orders', 'Orders', 'click.view_order'),
    ('pending', 'Pending Payments', 'app.view_pendingpayment'),
    ('atmos', 'ATMOS Transactions', 'atmos.view_atmostransaction'),
    ('payme', 'Payme Transactions', 'payme.view_paymetransaction'),
    ('promo', 'Promo Codes', 'click.view_promocode'),
    ('tools', 'Click Tools & Logs', 'click.view_order'),
]


@workspace_view('payments')
def payments(request):
    user = request.user
    tabs = [(k, label) for k, label, perm in PAYMENT_TABS if can(user, perm)]
    tab = request.GET.get('tab') or tabs[0][0]
    if tab not in dict(tabs):
        tab = tabs[0][0]
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    ctx = {'page_title': 'Payments', 'page_subtitle': 'Orders, transactions and promo codes',
           'tabs': tabs, 'tab': tab, 'q': q, 'status': status,
           'base_query': _query_without(request, 'page')}

    if tab == 'orders':
        qs = Order.objects.select_related('membership', 'conference_registration', 'promocode') \
            .annotate(payme_count=Count('payme_transactions')).order_by('-created_at')
        if q:
            cond = Q(membership__full_name__icontains=q) | Q(conference_registration__full_name__icontains=q) \
                | Q(click_trans_id__icontains=q) | Q(membership__email__icontains=q)
            if q.lstrip('#').isdigit():
                cond |= Q(pk=int(q.lstrip('#')))
            qs = qs.filter(cond)
        if status:
            qs = qs.filter(status=status)
        page, per_page = _page(request, qs)
        atmos = {}
        for txn in AtmosTransaction.objects.filter(account__in=[str(o.pk) for o in page.object_list]).order_by('-created_at'):
            atmos.setdefault(txn.account, txn)
        ctx.update(page=page, per_page=per_page, status_options=Order.STATUS_CHOICES,
                   rows=[{'o': o, 'atmos': atmos.get(str(o.pk)), 'url': admin_url('click_order_change', o.pk)}
                         for o in page.object_list])
    elif tab == 'pending':
        qs, _sort = people.filter_members({'q': q}, pending=True)
        page, per_page = _page(request, qs)
        ctx.update(page=page, per_page=per_page,
                   rows=people.member_rows(list(page.object_list), dict(people.membership_type_options())))
    elif tab == 'atmos':
        qs = AtmosTransaction.objects.all()
        if q:
            qs = qs.filter(Q(transaction_id__icontains=q) | Q(account__icontains=q)
                           | Q(card_number_masked__icontains=q) | Q(atmos_transaction_id__icontains=q))
        if status:
            qs = qs.filter(status=status)
        page, per_page = _page(request, qs)
        ctx.update(page=page, per_page=per_page,
                   status_options=AtmosTransaction._meta.get_field('status').choices,
                   rows=[{'t': t, 'url': admin_url('atmos_atmostransaction_change', t.pk)} for t in page.object_list])
    elif tab == 'payme':
        qs = PaymeTransaction.objects.select_related('order')
        if q:
            cond = Q(transaction_id__icontains=q)
            if q.lstrip('#').isdigit():
                cond |= Q(order_id=int(q.lstrip('#')))
            qs = qs.filter(cond)
        if status:
            qs = qs.filter(state=status)
        page, per_page = _page(request, qs)
        ctx.update(page=page, per_page=per_page,
                   status_options=[(str(k), v) for k, v in PaymeTransaction.STATE_CHOICES],
                   rows=[{'t': t, 'url': admin_url('payme_paymetransaction_change', t.pk)} for t in page.object_list])
    elif tab == 'promo':
        qs = PromoCode.objects.all()
        if q:
            qs = qs.filter(code__icontains=q)
        if status in ('active', 'inactive'):
            qs = qs.filter(is_active=status == 'active')
        page, per_page = _page(request, qs)
        ctx.update(page=page, per_page=per_page, status_options=[('active', 'Active'), ('inactive', 'Inactive')],
                   rows=[{'p': p, 'url': admin_url('click_promocode_change', p.pk)} for p in page.object_list],
                   add_url=admin_url('click_promocode_add') if can(user, 'click.add_promocode') else None)
    else:
        ctx.update(tools_url=admin_url('click_order_tools'))
    return render_ws(request, 'workspace/payments/list.html', ctx, 'payments')


# ── Partners ────────────────────────────────────────────────────────────────

@workspace_view('partners')
def partners(request):
    user = request.user
    qs = Partner.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q) | Q(phone_number__icontains=q)
                       | Q(company_name__icontains=q) | Q(position__icontains=q))
    country = request.GET.get('country', '')
    if country:
        qs = qs.filter(country=country)
    source = request.GET.get('source', '')
    if source:
        qs = qs.filter(source=source)
    page, per_page = _page(request, qs.order_by('full_name', 'id'))

    def distinct(field):
        return (Partner.objects.exclude(**{f'{field}__isnull': True}).exclude(**{field: ''})
                .order_by(field).values_list(field, flat=True).distinct())

    return render_ws(request, 'workspace/partners.html', {
        'page_title': 'Partners',
        'page_subtitle': 'Partner organisations and their contacts',
        'page': page, 'per_page': per_page, 'page_sizes': PAGE_SIZES, 'total': page.paginator.count,
        'rows': [{'obj': p, 'initials': people.initials(p.company_name or p.full_name or '?'),
                  'is_demo': people.is_demo_email(p.email),
                  'url': admin_url('app_partner_change', p.pk)} for p in page.object_list],
        'q': q, 'country': country, 'source': source,
        'countries': distinct('country'), 'sources': distinct('source'),
        'base_query': _query_without(request, 'page'),
        'import_url': admin_url('app_partner_import') if can(user, 'app.add_partner') else None,
        'export_url': admin_url('app_partner_export'),
        'add_url': admin_url('app_partner_add') if can(user, 'app.add_partner') else None,
        'bulk': _bulk_action(user, 'app_partner_changelist', CONTACT_EMAIL_ACTIONS, 'app.change_partner'),
        'message_url': _message_url(user, 'partner'),
    }, 'partners')


# ── Settings ────────────────────────────────────────────────────────────────

def _configured(*env_names):
    return all(os.getenv(name) for name in env_names)


@workspace_view('settings')
def settings_view(request):
    user = request.user
    integrations = integration_status()
    return render_ws(request, 'workspace/settings.html', {
        'page_title': 'Settings',
        'page_subtitle': 'Organisation, membership types, access and integrations',
        'membership_types': MembershipTypeConfig.objects.all() if can(user, 'app.view_membershiptypeconfig') else None,
        'type_add_url': admin_url('app_membershiptypeconfig_add') if can(user, 'app.add_membershiptypeconfig') else None,
        'can_change_types': can(user, 'app.change_membershiptypeconfig'),
        'user_count': User.objects.count() if can(user, 'auth.view_user') else None,
        'staff_count': User.objects.filter(is_staff=True).count() if can(user, 'auth.view_user') else None,
        'group_count': Group.objects.count() if can(user, 'auth.view_group') else None,
        'users_url': admin_url('auth_user_changelist') if can(user, 'auth.view_user') else None,
        'groups_url': admin_url('auth_group_changelist') if can(user, 'auth.view_group') else None,
        'integrations': integrations if user.is_superuser else None,
        'languages': Membership.LANGUAGE_CHOICES,
    }, 'settings')


# ── More tools ──────────────────────────────────────────────────────────────

@workspace_view('tools')
def tools(request):
    from django.contrib import admin

    app_list = admin.site.get_app_list(request)
    public_pages = [
        ('Membership application', reverse('membership_form')),
        ('TESOL Conference registration', reverse('conference_register')),
        ('30th Anniversary registration', reverse('anniversary_register')),
        ('Membership card preview', reverse('card_preview')),
        ('Membership terms (PDF)', reverse('membership_terms')),
        ('Privacy policy (PDF)', reverse('privacy_policy')),
    ]
    return render_ws(request, 'workspace/tools.html', {
        'page_title': 'More tools',
        'page_subtitle': 'Everything in the classic admin, plus public pages',
        'app_list': app_list,
        'public_pages': public_pages,
        'click_tools_url': admin_url('click_order_tools') if can(request.user, 'click.view_order') else None,
    }, 'tools')


# ── Website (uztea.uz content) ──────────────────────────────────────────────

@workspace_view('website')
def website(request):
    return render_ws(request, 'workspace/website.html', {
        'page_title': 'Website',
        'page_subtitle': 'Content of uztea.uz, managed from the workspace',
    }, 'website')


# ── SaaS Settings (organisation, language, integrations) ────────────────────

class OrganizationForm(forms.ModelForm):
    class Meta:
        from .models import OrganizationSettings
        model = OrganizationSettings
        fields = ['name', 'short_name', 'tagline', 'email', 'phone', 'website', 'address', 'default_language']
        widgets = {'address': forms.Textarea(attrs={'rows': 3})}


def integration_status():
    """Configured / not configured only — never the values."""
    from . import brevo
    return [
        {'name': 'Brevo (email)', 'icon': 'mail', 'ok': brevo.is_configured(),
         'note': 'Sends all emails through Brevo (BREVO_SMTP_LOGIN, BREVO_SMTP_KEY)'},
        {'name': 'Eskiz SMS', 'icon': 'message-square', 'ok': messaging.sms_mode() == 'live',
         'note': 'SMS from People and Partners (ESKIZ_EMAIL, ESKIZ_PASSWORD, ESKIZ_FROM)'},
        {'name': 'Click', 'icon': 'credit-card', 'ok': _configured('CLICK_SERVICE_ID', 'CLICK_MERCHANT_ID', 'CLICK_SECRET_KEY'),
         'note': 'Membership and conference checkout'},
        {'name': 'Payme', 'icon': 'credit-card', 'ok': bool(settings.PAYME_CASHBOX_ID and settings.PAYME_SECRET_KEY),
         'note': f'Environment: {settings.PAYME_ENV}'},
        {'name': 'Atmos', 'icon': 'wallet', 'ok': bool(settings.ATMOS_CONSUMER_KEY and settings.ATMOS_CONSUMER_SECRET),
         'note': 'UzCard / Humo and Visa / Mastercard'},
        {'name': 'Telegram', 'icon': 'send', 'ok': bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ADMIN_CHAT_ID),
         'note': 'Admin notifications about new applications'},
    ]


@workspace_view('saas')
def saas_settings(request):
    from django.contrib import messages as flash
    from .i18n import translate
    from .models import OrganizationSettings

    org = OrganizationSettings.get()
    can_edit = request.user.has_perm('workspace.change_organizationsettings')
    form = OrganizationForm(request.POST or None, instance=org)
    if request.method == 'POST' and can_edit and form.is_valid():
        form.save()
        flash.success(request, translate(request.session.get('uztea_lang') or form.cleaned_data['default_language'],
                                         'Settings saved.'))
        return redirect('workspace:saas')
    return render_ws(request, 'workspace/saas.html', {
        'page_title': 'SaaS Settings',
        'form': form, 'can_edit': can_edit, 'org': org,
        'integrations': integration_status() if request.user.is_superuser else None,
    }, 'saas')
