"""Скидки.

Правила (эталон):
- total_cents — сумма заказа в центах, int >= 0.
- Уровни: bronze 0%, silver 5%, gold 10%, platinum 15%.
- Неизвестный уровень или отрицательная сумма -> ValueError.
- Округление до целых центов — арифметическое (half-up): 294.5 -> 295.
"""

from decimal import Decimal, ROUND_HALF_UP

TIERS = {"bronze": 0, "silver": 5, "gold": 10, "platinum": 15}


def apply_tier_discount(total_cents: int, tier: str) -> int:
    """Вернуть сумму с учётом скидки уровня, в центах."""
    if total_cents < 0:
        raise ValueError("total_cents must be >= 0")
    pct = TIERS.get(tier)
    if pct is None:
        raise ValueError(f"unknown tier: {tier!r}")
    discounted = Decimal(total_cents) * (Decimal(100 - pct) / Decimal(100))
    return int(discounted.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def bulk_discount_percent(qty: int) -> int:
    """Скидка за объём в процентах: от 10 шт. — 3%, от 50 шт. — 7%, от 100 шт. — 12%.

    Граница «от N шт.» включает N (qty >= N).
    """
    if qty < 0:
        raise ValueError("qty must be >= 0")
    if qty > 100:
        return 12
    if qty >= 50:
        return 7
    if qty >= 10:
        return 3
    return 0
