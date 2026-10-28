"""People data for the workspace: member lists, previews, profiles, contacts.

Everything here is read-only. Records from different tables are never merged;
when the same email shows up in several places it is only pointed out.
"""
import re
from collections import defaultdict

from django.utils import timezone
from django.db.models import Case, IntegerField, Q, Value, When

from app.models import (
    AnniversaryRegistration,
    ConferenceRegistration,
    Membership,
    MembershipTypeConfig,
    Partner,
    TeacherBank,
)
from app import membership_lifecycle as lifecycle
from app.payment_status import (
    NO_PAYMENT,
    bulk_membership_payment_status,
    payment_status_style,
)

from .access import admin_url, can, initials

DEMO_EMAIL_DOMAIN = 'demo.uztea.test'

MEMBERSHIP_ID_RE = re.compile(r'^\s*(?:UZ)?0*(\d{1,9})\s*$', re.IGNORECASE)

MEMBER_SORTS = {
    'name': ('full_name', 'id'),
    '-name': ('-full_name', '-id'),
    'type': ('membership_type', 'full_name'),
    '-type': ('-membership_type', 'full_name'),
    'joined': ('created_at', 'id'),
    '-joined': ('-created_at', '-id'),
    'id': ('id',),
    '-id': ('-id',),
    # Validity is computed, not stored: these two are ordered in Python.
    'renewal': None,
    '-renewal': None,
}
DEFAULT_MEMBER_SORT = '-joined'

# Membership status filters (see app/membership_lifecycle.py). "Active" includes
# members whose renewal is due, because they are still valid.
STATUS_FILTERS = {
    'active': (lifecycle.ACTIVE, lifecycle.RENEWAL_DUE),
    'renewal_due': (lifecycle.RENEWAL_DUE,),
    'expired': (lifecycle.EXPIRED,),
    'pending': (lifecycle.PENDING,),
    'no_record': (lifecycle.NO_RECORD,),
}
STATUS_FILTER_LABELS = [
    ('active', 'Active'), ('renewal_due', 'Renewal due'), ('expired', 'Expired'),
    ('pending', 'Pending payment'), ('no_record', 'No payment record'),
]

# Membership fields grouped the way the application form groups them.
PROFILE_SECTIONS = [
    ('personal', 'Personal & Contacts', [
        'full_name', 'gender', 'date_of_birth', 'nationality', 'phone_number', 'email',
        'country', 'region_city', 'address', 'preferred_language', 'contact_method',
    ]),
    ('professional', 'Professional', [
        'position', 'institution_name', 'institution_type', 'experience', 'subjects', 'levels',
    ]),
    ('membership', 'Membership', [
        'membership_type', 'payment_method', 'interests', 'join_sig', 'sig_areas',
    ]),
    ('institutional', 'Institutional', [
        'institution_teachers_count', 'contact_person_name', 'contact_person_email',
        'collaboration_interest',
        'member_2_name', 'member_2_email', 'member_3_name', 'member_3_email',
        'member_4_name', 'member_4_email', 'member_5_name', 'member_5_email',
    ]),
    ('engagement', 'Engagement', [
        'contribution', 'participated_before', 'participation_details',
        'motivation', 'challenges', 'expectations',
    ]),
    ('consent', 'Consent', ['agree_terms', 'consent_data', 'agree_communication']),
]
# Shown elsewhere on the profile (header, documents, record card).
PROFILE_SPECIAL_FIELDS = {'id', 'payment_proof', 'is_pending_payment', 'created_at'}


def member_photo_url(email):
    """Photo the member uploaded in My profile, if any."""
    if not email:
        return ''
    from cabinet.models import MemberProfile
    profile = (MemberProfile.objects.filter(user__email__iexact=email).exclude(photo='')
               .select_related('user').first())
    return profile.photo.url if profile else ''


def membership_id(pk):
    return f'UZ{pk:06d}' if pk else '—'


def is_demo_email(email):
    return bool(email) and email.lower().endswith('@' + DEMO_EMAIL_DOMAIN)


def payment_badge(key):
    bg, fg, label = payment_status_style(key)
    tone = {
        'SUCCESS': 'success', 'PENDING': 'warning', 'OTP_SENT': 'info', 'CARD_BOUND': 'info',
        'FAILED': 'danger', 'CANCELLED': 'muted', NO_PAYMENT: 'muted',
    }.get(key, 'muted')
    return {'key': key, 'label': label, 'tone': tone}


def membership_type_options():
    names = {c.membership_type: c.name for c in MembershipTypeConfig.objects.all()}
    fallback = dict(Membership.MEMBERSHIP_TYPE_CHOICES)
    codes = list(names)
    for code in Membership.objects.order_by().values_list('membership_type', flat=True).distinct():
        if code and code not in names:
            codes.append(code)
    return [
        (code, names.get(code) or fallback.get(code) or code.replace('-', ' ').replace('_', ' ').title())
        for code in codes
    ]


def search_memberships(qs, q):
    q = (q or '').strip()
    if not q:
        return qs
    cond = Q(full_name__icontains=q) | Q(email__icontains=q) | Q(institution_name__icontains=q)
    match = MEMBERSHIP_ID_RE.match(q)
    if match:
        cond |= Q(pk=int(match.group(1)))
    return qs.filter(cond)


def _ordered_by_pks(qs, pks):
    if not pks:
        return qs.none()
    order = Case(*[When(pk=pk, then=Value(i)) for i, pk in enumerate(pks)], output_field=IntegerField())
    return qs.filter(pk__in=pks).order_by(order)


def filter_members(params, pending):
    """Apply list params (q, type, position, language, institution_type, country, status, sort)."""
    qs = Membership.objects.filter(is_pending_payment=pending)
    qs = search_memberships(qs, params.get('q'))
    for field, key in (
        ('membership_type', 'type'), ('position', 'position'), ('preferred_language', 'language'),
        ('institution_type', 'institution_type'), ('country', 'country'),
    ):
        value = params.get(key)
        if value:
            qs = qs.filter(**{field: value})
    subscribed = params.get('subscribed')
    if subscribed in ('yes', 'no'):
        qs = qs.filter(agree_communication=subscribed == 'yes')
    status = params.get('status')
    if status in STATUS_FILTERS:
        qs = qs.filter(pk__in=lifecycle.ids_with_status(qs, STATUS_FILTERS[status]))
    sort = params.get('sort') if params.get('sort') in MEMBER_SORTS else DEFAULT_MEMBER_SORT
    if MEMBER_SORTS[sort] is None:
        # Soonest renewal first; members without a validity date go last.
        statuses = lifecycle.bulk_status(list(qs.values_list('pk', flat=True)))
        dated = sorted((s['valid_until'], pk) for pk, s in statuses.items() if s['valid_until'])
        undated = sorted(pk for pk, s in statuses.items() if not s['valid_until'])
        pks = [pk for _when, pk in dated]
        if sort == '-renewal':
            pks.reverse()
        return _ordered_by_pks(qs, pks + undated), sort
    return qs.order_by(*MEMBER_SORTS[sort]), sort


def member_rows(memberships, type_names):
    statuses = bulk_membership_payment_status(memberships)
    member_status = lifecycle.bulk_status(memberships)
    rows = []
    for m in memberships:
        rows.append({
            'obj': m,
            'pk': m.pk,
            'membership_id': membership_id(m.pk),
            'initials': initials(m.full_name),
            'type_name': type_names.get(m.membership_type) or m.membership_type,
            'payment': payment_badge(statuses.get(m.pk, NO_PAYMENT)),
            'status': member_status[m.pk],
            'is_demo': is_demo_email(m.email),
        })
    return rows


def _display(obj, field):
    value = getattr(obj, field.name)
    if field.choices:
        value = getattr(obj, f'get_{field.name}_display')()
    if field.name == 'membership_type':
        value = obj.get_membership_type_display()
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if value in (None, ''):
        return None
    return value


def profile_sections(membership):
    fields = {f.name: f for f in Membership._meta.concrete_fields}
    seen = set(PROFILE_SPECIAL_FIELDS)
    sections = []
    for key, title, names in PROFILE_SECTIONS:
        items = []
        for name in names:
            if name in fields:
                seen.add(name)
                items.append({'label': fields[name].verbose_name.capitalize(),
                              'value': _display(membership, fields[name])})
        sections.append({'key': key, 'title': title, 'items': items})
    # Any field added to the model later still shows up.
    extra = [{'label': f.verbose_name.capitalize(), 'value': _display(membership, f)}
             for name, f in fields.items() if name not in seen]
    if extra:
        sections.append({'key': 'other', 'title': 'Other', 'items': extra})
    return sections


def membership_activity(membership):
    """Real events from existing records, newest first."""
    from atmos.models import AtmosTransaction

    events = []
    if membership.created_at:
        events.append({'when': membership.created_at, 'icon': 'file-text', 'tone': 'blue',
                       'title': 'Application submitted',
                       'text': f'{membership.get_membership_type_display()} application'})
    orders = list(membership.orders.prefetch_related('payme_transactions').order_by('-created_at'))
    for order in orders:
        events.append({'when': order.created_at, 'icon': 'credit-card', 'tone': 'orange',
                       'title': f'Order #{order.pk} created',
                       'text': f'{order.amount:,.0f} UZS · now {order.get_status_display()}'.replace(',', ' ')})
        for txn in order.payme_transactions.all():
            if txn.performed_at:
                events.append({'when': txn.performed_at, 'icon': 'check', 'tone': 'green',
                               'title': 'Payme payment performed', 'text': f'Order #{order.pk}'})
            if txn.cancelled_at:
                events.append({'when': txn.cancelled_at, 'icon': 'x', 'tone': 'muted',
                               'title': 'Payme transaction cancelled', 'text': f'Order #{order.pk}'})
    if orders:
        for txn in AtmosTransaction.objects.filter(account__in=[str(o.pk) for o in orders]):
            events.append({'when': txn.created_at, 'icon': 'wallet',
                           'tone': 'green' if txn.status == 'SUCCESS' else 'muted',
                           'title': f'Atmos transaction · {txn.get_status_display()}',
                           'text': f'Order #{txn.account} · {txn.amount_uzs:,.0f} UZS'.replace(',', ' ')})
    from cabinet.models import ProfileChange
    for change in ProfileChange.objects.filter(membership=membership)[:20]:
        events.append({'when': change.created_at, 'icon': 'pencil', 'tone': 'blue',
                       'title': 'Profile updated by the member',
                       'text': '; '.join(f'{k}: {v[0] or "—"} → {v[1] or "—"}' for k, v in change.changes.items())[:300]})
    from .models import MessageLog
    for msg in MessageLog.objects.filter(source='member', recipient_id=membership.pk).exclude(status=MessageLog.SKIPPED)[:20]:
        events.append({'when': msg.created_at, 'icon': 'mail' if msg.channel == MessageLog.CHANNEL_EMAIL else 'message-square',
                       'tone': 'danger' if msg.status == MessageLog.FAILED else 'purple',
                       'title': f'{msg.get_channel_display()} {msg.get_status_display().lower()}',
                       'text': msg.subject or msg.body[:80]})
    from app import membership_lifecycle as lifecycle_mod
    status = lifecycle_mod.membership_status(membership)
    if status['paid_at']:
        events.append({'when': status['paid_at'], 'icon': 'check-circle', 'tone': 'green',
                       'title': 'Membership active',
                       'text': f"Valid until {timezone.localtime(status['valid_until']):%d %b %Y}"})
    events.sort(key=lambda e: e['when'], reverse=True)
    return events


def related_by_email(user, email, exclude_membership=None):
    """Records in other tables with the same email. Shown as hints, never merged."""
    if not email:
        return []
    sources = [
        ('app.view_membership', Membership, 'Membership application', 'full_name',
         lambda o: o.get_membership_type_display()),
        ('app.view_conferenceregistration', ConferenceRegistration, 'TESOL Conference', 'full_name',
         lambda o: o.organization),
        ('app.view_anniversaryregistration', AnniversaryRegistration, '30th Anniversary', 'full_name',
         lambda o: f'Member: {o.get_membership_status_display()}'),
        ('app.view_teacherbank', TeacherBank, 'Teachers Bank', 'full_name', lambda o: o.source or ''),
        ('app.view_partner', Partner, 'Partners', 'full_name', lambda o: o.company_name or ''),
    ]
    found = []
    for perm, model, label, name_field, detail in sources:
        if not can(user, perm):
            continue
        qs = model.objects.filter(email__iexact=email)
        if model is Membership and exclude_membership is not None:
            qs = qs.exclude(pk=exclude_membership.pk)
        meta = model._meta
        for obj in qs[:20]:
            found.append({
                'source': label,
                'name': getattr(obj, name_field) or '—',
                'detail': detail(obj),
                'when': getattr(obj, 'created_at', None),
                'url': admin_url(f'{meta.app_label}_{meta.model_name}_change', obj.pk),
            })
    return found


# ── All contacts ────────────────────────────────────────────────────────────

CONTACT_SOURCES = [
    # key, label, permission, model, name, phone field, extra filter
    ('member', 'Member', 'app.view_membership', Membership, 'phone_number', {'is_pending_payment': False}),
    ('pending', 'Pending payment', 'app.view_pendingpayment', Membership, 'phone_number', {'is_pending_payment': True}),
    ('teachers_bank', 'Teachers Bank', 'app.view_teacherbank', TeacherBank, 'phone_number', {}),
    ('partner', 'Partner', 'app.view_partner', Partner, 'phone_number', {}),
    ('tesol', 'TESOL Conference', 'app.view_conferenceregistration', ConferenceRegistration, 'mobile_phone', {}),
    ('anniversary', '30th Anniversary', 'app.view_anniversaryregistration', AnniversaryRegistration, 'phone_number', {}),
]


INSTITUTION_MEMBER_SLOTS = (2, 3, 4, 5)
INSTITUTION_MEMBER_SOURCE = ('institution_member', 'Institution member')


def institution_members(membership):
    """People listed inside an institutional membership (member 2–5), each shown as a person.

    They have no record of their own: their membership status is the institution's.
    """
    people = []
    for slot in INSTITUTION_MEMBER_SLOTS:
        name = (getattr(membership, f'member_{slot}_name') or '').strip()
        email = (getattr(membership, f'member_{slot}_email') or '').strip()
        if name or email:
            people.append({'slot': slot, 'name': name or '—', 'email': email, 'initials': initials(name or email)})
    return people


def contact_sources_for(user):
    return [s for s in CONTACT_SOURCES if can(user, s[2])]


def all_contacts(user, q='', source=''):
    """Every contact the user may see, one row per record (no merging)."""
    q = (q or '').strip()
    rows = []
    email_sources = defaultdict(set)
    for key, label, _perm, model, phone_field, extra in contact_sources_for(user):
        base = model.objects.filter(**extra)
        for email in base.exclude(email__isnull=True).exclude(email='').values_list('email', flat=True):
            email_sources[email.lower()].add(label)
        if source and source != key:
            continue
        qs = base
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q) | Q(**{f'{phone_field}__icontains': q}))
        meta = model._meta
        for pk, name, email, phone in qs.values_list('pk', 'full_name', 'email', phone_field):
            rows.append({
                'source_key': key, 'source': label, 'pk': pk,
                'name': name or '—', 'email': email or '', 'phone': phone or '',
                'initials': initials(name or email or '?'),
                'is_member_record': model is Membership,
                'admin_url': admin_url(f'{meta.app_label}_{meta.model_name}_change', pk),
                'is_demo': is_demo_email(email),
            })
    if can(user, 'app.view_membership') and source in ('', INSTITUTION_MEMBER_SOURCE[0]):
        has_members = Q()
        for slot in INSTITUTION_MEMBER_SLOTS:
            has_members |= Q(**{f'member_{slot}_name__gt': ''}) | Q(**{f'member_{slot}_email__gt': ''})
        for m in Membership.objects.filter(has_members):
            for person in institution_members(m):
                if person['email']:
                    email_sources[person['email'].lower()].add(INSTITUTION_MEMBER_SOURCE[1])
                text = f"{person['name']} {person['email']}".lower()
                if q and q.lower() not in text:
                    continue
                rows.append({
                    'source_key': INSTITUTION_MEMBER_SOURCE[0], 'source': INSTITUTION_MEMBER_SOURCE[1],
                    'pk': m.pk, 'name': person['name'], 'email': person['email'], 'phone': '',
                    'initials': person['initials'], 'is_member_record': True,
                    'institution': m.institution_name or m.full_name,
                    'admin_url': None, 'is_demo': is_demo_email(person['email']) or is_demo_email(m.email),
                })
    for row in rows:
        others = email_sources.get(row['email'].lower(), set()) - {row['source']} if row['email'] else set()
        row['also_in'] = sorted(others)
    rows.sort(key=lambda r: (r['name'].lower(), r['source']))
    return rows
