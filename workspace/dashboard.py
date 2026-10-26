"""Home dashboard: figures and chart geometry computed from existing records.

Read-only. Every number comes from the database at request time; nothing is
cached or invented. Revenue uses the same "paid" rule as the admin revenue
cards: an order with status 'paid' or with a successful Atmos transaction.
"""
from collections import Counter, OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import math

from django.db.models import Q
from django.utils import timezone

from app.models import AnniversaryRegistration, ConferenceRegistration, Membership
from app.payment_status import NO_PAYMENT, bulk_membership_payment_status
from atmos.models import AtmosTransaction
from click.models import Order

from .access import can
from .people import membership_type_options

PERIODS = OrderedDict([
    ('30d', {'label': '30 days', 'days': 30, 'unit': 'day'}),
    ('90d', {'label': '90 days', 'days': 90, 'unit': 'week'}),
    ('12m', {'label': '12 months', 'days': None, 'months': 12, 'unit': 'month'}),
    ('all', {'label': 'All time', 'days': None, 'unit': 'month'}),
])
DEFAULT_PERIOD = '12m'
MAX_ALL_TIME_MONTHS = 36

# Status colours carry an icon/label next to them, never colour alone.
STATUS_COLORS = {
    'SUCCESS': '#0ca30c', 'PENDING': '#fab219', 'OTP_SENT': '#fab219', 'CARD_BOUND': '#fab219',
    'FAILED': '#d03b3b', 'CANCELLED': '#9aa4b2', NO_PAYMENT: '#c3cad6',
}
STATUS_LABELS = {
    'SUCCESS': 'Paid', 'PENDING': 'Pending', 'OTP_SENT': 'In progress (OTP sent)',
    'CARD_BOUND': 'In progress (card bound)', 'FAILED': 'Failed', 'CANCELLED': 'Cancelled',
    NO_PAYMENT: 'No payment yet',
}
STATUS_ORDER = ['SUCCESS', 'PENDING', 'OTP_SENT', 'CARD_BOUND', 'FAILED', 'CANCELLED', NO_PAYMENT]


# ── Time ranges and buckets ─────────────────────────────────────────────────

def _month_start(d, back=0):
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _next_month(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def bucket_key(dt, unit):
    d = timezone.localtime(dt).date() if isinstance(dt, datetime) else dt
    if unit == 'day':
        return d
    if unit == 'week':
        return d - timedelta(days=d.weekday())
    return d.replace(day=1)


def resolve_period(key, first_record=None, now=None):
    """Return the selected period with aware start/end and the previous period."""
    key = key if key in PERIODS else DEFAULT_PERIOD
    spec = PERIODS[key]
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    unit = spec['unit']

    if spec.get('days'):
        start_day = today - timedelta(days=spec['days'] - 1)
    elif spec.get('months'):
        start_day = _month_start(today, spec['months'] - 1)
    else:
        first = timezone.localtime(first_record).date() if first_record else today
        start_day = max(_month_start(first), _month_start(today, MAX_ALL_TIME_MONTHS - 1))

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_day, time.min), tz)
    length = now - start
    return {
        'key': key, 'label': spec['label'], 'unit': unit,
        'start': start, 'end': now, 'start_day': start_day, 'today': today,
        'prev_start': start - length, 'prev_end': start,
        'is_all': key == 'all',
    }


def bucket_list(period):
    unit, day, today = period['unit'], bucket_key(period['start_day'], period['unit']), period['today']
    out = []
    while day <= today:
        out.append(day)
        if unit == 'day':
            day += timedelta(days=1)
        elif unit == 'week':
            day += timedelta(days=7)
        else:
            day = _next_month(day)
    return out


def bucket_label(d, unit, short=False):
    if unit == 'month':
        return d.strftime('%b' if short else '%b %Y')
    return d.strftime('%d %b')


# ── Number formatting ───────────────────────────────────────────────────────

def compact(value):
    value = float(value or 0)
    for div, suffix in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if abs(value) >= div:
            text = f'{value / div:.1f}'.rstrip('0').rstrip('.')
            return text + suffix
    return f'{value:,.0f}'.replace(',', ' ')


def full_number(value):
    return f'{float(value or 0):,.0f}'.replace(',', ' ')


def nice_ticks(max_value, count=4):
    if max_value <= 0:
        return [0, 1]
    raw = max_value / count
    power = 10 ** math.floor(math.log10(raw))
    step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)
    if step < 1:
        step = 1
    top = step * math.ceil(max_value / step)
    ticks, v = [], 0
    while v <= top + 1e-9:
        ticks.append(v)
        v += step
    return ticks


# ── Chart builders (plain dicts the template renders) ───────────────────────

def column_chart(buckets, series, unit, money=False):
    """Stacked (or single) column chart.

    series: list of {'key', 'label', 'color', 'values': {bucket: number}}
    """
    totals = [sum(s['values'].get(b, 0) for s in series) for b in buckets]
    ticks = nice_ticks(max(totals) if totals else 0)
    top = ticks[-1] or 1
    label_every = max(1, math.ceil(len(buckets) / 6))
    columns = []
    for i, b in enumerate(buckets):
        segments = []
        for s in series:
            v = s['values'].get(b, 0)
            if v:
                segments.append({'color': s['color'], 'pct': round(float(v) / top * 100, 3), 'label': s['label'],
                                 'value': full_number(v) + (' UZS' if money else '')})
        if segments:
            segments[-1]['is_top'] = True
        tip_lines = [f"{seg['label']}: {seg['value']}" for seg in segments] if len(series) > 1 else []
        columns.append({
            'label': bucket_label(b, unit, short=True),
            'full_label': bucket_label(b, unit) + (' (week)' if unit == 'week' else ''),
            'show_label': i % label_every == 0,
            'segments': list(reversed(segments)),  # top segment first for column-reverse stacking
            'total': full_number(totals[i]) + (' UZS' if money else ''),
            'tip': ' · '.join(tip_lines),
            'is_last': i == len(buckets) - 1,
        })
    return {
        'columns': columns,
        'ticks': [{'label': compact(t), 'pct': round(t / top * 100, 3)} for t in reversed(ticks)],
        'series': [{'label': s['label'], 'color': s['color'],
                    'total': full_number(sum(s['values'].values())) + (' UZS' if money else '')} for s in series],
        'is_empty': not any(totals),
        'money': money,
    }


def bar_list(items, color='#2a78d6', limit=None, other_label='Other'):
    """Horizontal bars, sorted by value. items: [(label, value)] or [(label, value, color)]."""
    rows = [i if len(i) == 3 else (i[0], i[1], color) for i in items if i[1]]
    rows.sort(key=lambda r: r[1], reverse=True)
    if limit and len(rows) > limit:
        rest = sum(r[1] for r in rows[limit - 1:])
        rows = rows[:limit - 1] + [(other_label, rest, '#9aa4b2')]
    total = sum(r[1] for r in rows) or 1
    top = max((r[1] for r in rows), default=0) or 1
    return {
        'rows': [{'label': label, 'value': full_number(v), 'pct': round(v / top * 100, 2),
                  'share': round(v / total * 100), 'color': c} for label, v, c in rows],
        'total': full_number(sum(r[1] for r in rows)) if rows else '0',
        'is_empty': not rows,
    }


def delta(current, previous, period):
    if period['is_all'] or previous in (None, 0):
        return None
    change = (float(current) - float(previous)) / float(previous) * 100
    return {'pct': f'{abs(change):.0f}%', 'up': change > 0, 'flat': round(change) == 0,
            'vs': f"vs previous {period['label']}"}


# ── Data ────────────────────────────────────────────────────────────────────

def _paid_order_ids():
    atmos_ok = [int(a) for a in AtmosTransaction.objects.filter(status='SUCCESS')
                .values_list('account', flat=True) if str(a).isdigit()]
    return Q(status='paid') | Q(pk__in=atmos_ok)


def build(user, period_key):
    first = Membership.objects.order_by('created_at').values_list('created_at', flat=True).first()
    period = resolve_period(period_key, first)
    buckets = bucket_list(period)
    unit = period['unit']
    in_period = Q(created_at__gte=period['start'], created_at__lte=period['end'])
    in_prev = Q(created_at__gte=period['prev_start'], created_at__lt=period['prev_end'])

    data = {'period': period, 'periods': [(k, v['label']) for k, v in PERIODS.items()],
            'tiles': [], 'charts': {}}

    if can(user, 'app.view_membership', 'app.view_pendingpayment'):
        apps = Membership.objects.filter(in_period)
        new_now = apps.count()
        new_prev = Membership.objects.filter(in_prev).count()
        data['tiles'].append({'label': 'Members list', 'value': full_number(Membership.objects.filter(is_pending_payment=False).count()),
                              'note': 'all time, excluding Pending Payment', 'icon': 'users'})
        data['tiles'].append({'label': 'New applications', 'value': full_number(new_now),
                              'note': period['label'], 'delta': delta(new_now, new_prev, period), 'icon': 'id-card'})

        per_bucket = Counter(bucket_key(dt, unit) for dt in apps.values_list('created_at', flat=True))
        data['charts']['applications'] = column_chart(
            buckets, [{'key': 'apps', 'label': 'Applications', 'color': '#2a78d6', 'values': per_bucket}], unit)

        type_names = dict(membership_type_options())
        by_type = Counter(apps.values_list('membership_type', flat=True))
        data['charts']['types'] = bar_list([(type_names.get(k, k), v) for k, v in by_type.items()])

        member_list = list(apps.only('pk'))
        statuses = Counter(bulk_membership_payment_status(member_list).values())
        data['charts']['payment_status'] = bar_list(
            [(STATUS_LABELS.get(k, k), statuses[k], STATUS_COLORS.get(k, '#9aa4b2'))
             for k in STATUS_ORDER + [k for k in statuses if k not in STATUS_ORDER] if statuses.get(k)])
        paid_share = statuses.get('SUCCESS', 0)
        data['tiles'].append({'label': 'Paid applications', 'value': f'{round(paid_share / new_now * 100)}%' if new_now else '—',
                              'note': f'{full_number(paid_share)} of {full_number(new_now)} in {period["label"]}', 'icon': 'check-circle'})

        regions = Counter((r or '').strip().title() or 'Not given' for r in apps.values_list('region_city', flat=True))
        data['charts']['regions'] = bar_list(list(regions.items()), limit=8)
        positions = dict(Membership.POSITION_CHOICES)
        data['charts']['positions'] = bar_list(
            [(positions.get(k, k), v) for k, v in Counter(apps.values_list('position', flat=True)).items()])
        languages = dict(Membership.LANGUAGE_CHOICES)
        data['charts']['languages'] = bar_list(
            [(languages.get(k, k), v) for k, v in Counter(apps.values_list('preferred_language', flat=True)).items()])

    if can(user, 'click.view_order'):
        paid = Order.objects.filter(_paid_order_ids())
        revenue_now = paid.filter(in_period)
        rev_member, rev_tesol = Counter(), Counter()
        total_now = Decimal(0)
        for created, amount, member_id in revenue_now.values_list('created_at', 'amount', 'membership_id'):
            (rev_member if member_id else rev_tesol)[bucket_key(created, unit)] += float(amount)
            total_now += amount
        total_prev = sum(paid.filter(in_prev).values_list('amount', flat=True), Decimal(0))
        data['tiles'].insert(2, {'label': 'Revenue', 'value': compact(total_now) + ' UZS', 'title': full_number(total_now) + ' UZS',
                                 'note': period['label'], 'delta': delta(total_now, total_prev, period), 'icon': 'credit-card'})
        data['charts']['revenue'] = column_chart(buckets, [
            {'key': 'membership', 'label': 'Membership', 'color': '#2a78d6', 'values': rev_member},
            {'key': 'tesol', 'label': 'TESOL Conference', 'color': '#eb6834', 'values': rev_tesol},
        ], unit, money=True)
        pending_orders = Order.objects.filter(status__in=('pending', 'processing')).filter(in_period).count()
        data['pending_orders'] = pending_orders

    events = []
    if can(user, 'app.view_conferenceregistration'):
        tesol = ConferenceRegistration.objects.filter(in_period)
        n = tesol.count()
        paid_n = tesol.filter(order__in=Order.objects.filter(_paid_order_ids())).count() if can(user, 'click.view_order') else None
        events.append(('TESOL Conference', n, paid_n))
    if can(user, 'app.view_anniversaryregistration'):
        events.append(('30th Anniversary', AnniversaryRegistration.objects.filter(in_period).count(), None))
    if events:
        chart = bar_list([(label, n) for label, n, _paid in events], color='#2a78d6')
        notes = {label: paid_n for label, _n, paid_n in events}
        for row in chart['rows']:
            paid_n = notes.get(row['label'])
            row['note'] = f'{full_number(paid_n)} paid' if paid_n is not None else ''
        data['charts']['events'] = chart

    return data
