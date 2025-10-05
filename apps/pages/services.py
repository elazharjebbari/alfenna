# apps/pages/services.py
from decimal import Decimal, ROUND_HALF_UP

def compute_promotion_price(course, default_reference: int = 169, discount_pct: int = 30) -> int:
    """
    Calcule un prix promo -X% ; si course.price absent, applique -X% sur default_reference.
    Retourne un entier MAD.
    """
    try:
        base = getattr(course, "price", None)
        if base is None:
            base_amount = Decimal(default_reference)
        else:
            base_amount = Decimal(str(base))
    except Exception:
        base_amount = Decimal(default_reference)

    pct = Decimal(discount_pct) / Decimal(100)
    promo = base_amount * (Decimal(1) - pct)
    return int(promo.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
