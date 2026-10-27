"""Membership status computed from existing payment records (read-only).

Approved rules (2026-10-27):
- A membership becomes Active when a payment succeeds.
- It is valid for 12 months (365 days, same as the welcome email) from the date of
  the latest successful payment.
- "Renewal due" = still active, 30 days or less left.
- "Expired" = the validity date has passed.
- No successful payment yet: "Pending payment" when an order exists, otherwise
  "No payment record" (for example members imported from the old site).

A successful payment is an order with status 'paid' or with a SUCCESS Atmos
transaction (the same rule as the admin revenue cards). Its date is the Payme
performed_at time, else the Atmos success time, else the order's last update
(Click and the free-promo path set 'paid' and save the order at payment time).
Nothing is stored, so changing these rules never needs a migration.
"""
from datetime import timedelta

from django.utils import timezone

VALIDITY = timedelta(days=365)
RENEWAL_WINDOW = timedelta(days=30)

ACTIVE = 'active'
RENEWAL_DUE = 'renewal_due'
EXPIRED = 'expired'
PENDING = 'pending'
NO_RECORD = 'no_record'

STATUS_LABELS = {
    ACTIVE: 'Active',
    RENEWAL_DUE: 'Renewal due',
    EXPIRED: 'Expired',
    PENDING: 'Pending payment',
    NO_RECORD: 'No payment record',
}
STATUS_TONES = {
    ACTIVE: 'success', RENEWAL_DUE: 'warning', EXPIRED: 'muted', PENDING: 'warning', NO_RECORD: 'muted',
}


def bulk_paid_at(membership_ids):
    """{membership_pk: datetime of the latest successful payment} (absent = never paid)."""
    from atmos.models import AtmosTransaction
    from click.models import Order
    from payme.models import PaymeTransaction

    ids = list(membership_ids)
    if not ids:
        return {}
    orders = list(Order.objects.filter(membership_id__in=ids).values('id', 'membership_id', 'status', 'updated_at'))
    if not orders:
        return {}
    by_id = {str(o['id']): o for o in orders}

    atmos_success = {}
    for account, updated in (AtmosTransaction.objects
                             .filter(account__in=list(by_id), status='SUCCESS')
                             .values_list('account', 'updated_at')):
        if account not in atmos_success or updated > atmos_success[account]:
            atmos_success[account] = updated

    payme_performed = {}
    for order_id, performed in (PaymeTransaction.objects
                                .filter(order_id__in=[o['id'] for o in orders], state=2, performed_at__isnull=False)
                                .values_list('order_id', 'performed_at')):
        key = str(order_id)
        if key not in payme_performed or performed > payme_performed[key]:
            payme_performed[key] = performed

    result = {}
    for key, order in by_id.items():
        if order['status'] != 'paid' and key not in atmos_success:
            continue
        paid_at = payme_performed.get(key) or atmos_success.get(key) or order['updated_at']
        member = order['membership_id']
        if member not in result or paid_at > result[member]:
            result[member] = paid_at
    return result


def status_for(paid_at, has_orders, now=None):
    now = now or timezone.now()
    if paid_at is None:
        return {'key': PENDING if has_orders else NO_RECORD, 'paid_at': None, 'valid_until': None, 'days_left': None}
    valid_until = paid_at + VALIDITY
    left = valid_until - now
    if left <= timedelta(0):
        key = EXPIRED
    elif left <= RENEWAL_WINDOW:
        key = RENEWAL_DUE
    else:
        key = ACTIVE
    return {'key': key, 'paid_at': paid_at, 'valid_until': valid_until, 'days_left': max(left.days, 0)}


def bulk_status(memberships_or_ids, now=None):
    """{membership_pk: {'key', 'label', 'tone', 'paid_at', 'valid_until', 'days_left'}}."""
    from click.models import Order

    ids = [getattr(m, 'pk', m) for m in memberships_or_ids]
    paid = bulk_paid_at(ids)
    with_orders = set(Order.objects.filter(membership_id__in=ids).values_list('membership_id', flat=True)) if ids else set()
    out = {}
    for pk in ids:
        info = status_for(paid.get(pk), pk in with_orders, now)
        info['label'] = STATUS_LABELS[info['key']]
        info['tone'] = STATUS_TONES[info['key']]
        out[pk] = info
    return out


def membership_status(membership, now=None):
    return bulk_status([membership.pk], now)[membership.pk]


def ids_with_status(queryset, keys, now=None):
    """Primary keys from `queryset` whose status is in `keys` (computed in Python)."""
    ids = list(queryset.values_list('pk', flat=True))
    statuses = bulk_status(ids, now)
    return [pk for pk in ids if statuses[pk]['key'] in keys]
