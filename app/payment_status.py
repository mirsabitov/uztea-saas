"""Read-only payment status of a membership, shared by the admin and the workspace.

This only *reads* orders and transactions to describe them; it never changes
payment state. Order of precedence matches the original admin column:
the latest Atmos transaction for any of the membership's orders wins,
otherwise the most recently updated order decides.
"""

NO_PAYMENT = 'NO_PAYMENT'

# key -> (background, foreground, label)
PAYMENT_STATUS_STYLES = {
    'SUCCESS':    ('#dcfce7', '#15803d', 'Success'),
    'OTP_SENT':   ('#dbeafe', '#1d4ed8', 'OTP Sent'),
    'CARD_BOUND': ('#e0e7ff', '#4338ca', 'Card Bound'),
    'PENDING':    ('#fff7ed', '#c2410c', 'Pending'),
    'FAILED':     ('#fee2e2', '#b91c1c', 'Failed'),
    'CANCELLED':  ('#f1f5f9', '#64748b', 'Cancelled'),
    NO_PAYMENT:   ('#f1f5f9', '#64748b', 'No payment'),
}


def membership_payment_status(membership):
    """Return a status key such as 'SUCCESS', 'PENDING' or NO_PAYMENT."""
    from atmos.models import AtmosTransaction

    order_ids = [str(oid) for oid in membership.orders.values_list('id', flat=True)]
    if order_ids:
        txn = (AtmosTransaction.objects
               .filter(account__in=order_ids)
               .order_by('-created_at')
               .only('status')
               .first())
        if txn is not None:
            return txn.status

    order = membership.orders.order_by('-updated_at').only('status').first()
    if order is None:
        return NO_PAYMENT
    if order.status == 'paid':
        return 'SUCCESS'
    if order.status == 'failed':
        return 'FAILED'
    return 'PENDING'


def bulk_membership_payment_status(memberships):
    """Same rules as membership_payment_status() for many memberships in 2 queries.

    Returns {membership_pk: status_key}.
    """
    from atmos.models import AtmosTransaction
    from click.models import Order

    pks = [m.pk for m in memberships]
    if not pks:
        return {}

    orders = list(
        Order.objects.filter(membership_id__in=pks)
        .values('id', 'membership_id', 'status', 'updated_at')
    )
    order_owner = {str(o['id']): o['membership_id'] for o in orders}

    latest_txn = {}
    if order_owner:
        for txn in (AtmosTransaction.objects
                    .filter(account__in=list(order_owner))
                    .order_by('-created_at')
                    .values('account', 'status')):
            latest_txn.setdefault(order_owner[txn['account']], txn['status'])

    latest_order = {}
    for order in sorted(orders, key=lambda o: o['updated_at'], reverse=True):
        latest_order.setdefault(order['membership_id'], order['status'])

    result = {}
    for pk in pks:
        if pk in latest_txn:
            result[pk] = latest_txn[pk]
        elif pk not in latest_order:
            result[pk] = NO_PAYMENT
        elif latest_order[pk] == 'paid':
            result[pk] = 'SUCCESS'
        elif latest_order[pk] == 'failed':
            result[pk] = 'FAILED'
        else:
            result[pk] = 'PENDING'
    return result


def payment_status_style(key):
    return PAYMENT_STATUS_STYLES.get(key, ('#f1f5f9', '#64748b', key))
