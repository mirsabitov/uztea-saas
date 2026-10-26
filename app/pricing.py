# Fallback prices — used only if no active MembershipTypeConfig row exists.
PRICES = {
    'basic': 1000.0,
    'student': 206000.0,
    'teacher': 412000.0,
    'institutional': 2000000.0,
}


def get_membership_price(membership_type: str) -> float:
    """Single source of truth for membership price.

    Reads the live price from MembershipTypeConfig (editable in admin);
    falls back to the hardcoded PRICES if no config/DB is available.
    """
    try:
        from .models import MembershipTypeConfig
        cfg = MembershipTypeConfig.objects.filter(membership_type=membership_type).first()
        if cfg is not None:
            return float(cfg.price)
    except Exception:
        pass
    return float(PRICES.get(membership_type, 0.0))


def format_membership_price(membership_type: str) -> str:
    price = get_membership_price(membership_type)
    if price <= 0:
        return 'Free'
    return f'{price:,.0f} UZS'
