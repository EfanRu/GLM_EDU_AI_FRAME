"""Разбиение суммы заказа на части.

Правила (эталон):
- Все суммы — целые центы (int).
- split_payment: parts частей, остаток от деления раздаётся по одному центу
  первым частям. Сумма частей обязана равняться исходной сумме.
- split_weighted: пропорционально весам, методом наибольших остатков
  (сначала floor, затем недостающие центы получают части с наибольшей
  дробной частью; при равенстве — та, что раньше в списке).
"""

import math


def split_payment(amount_cents: int, parts: int) -> list:
    """Разбить amount_cents на parts частей целыми центами.

    Если amount_cents < parts — ValueError (не хватит по центу на часть).
    """
    if amount_cents < 0:
        raise ValueError("amount_cents must be >= 0")
    if parts < 1:
        raise ValueError("parts must be >= 1")
    if amount_cents < parts:
        raise ValueError("amount_cents is less than number of parts")
    base, rem = divmod(amount_cents, parts)
    return [base] * parts


def split_weighted(amount_cents: int, weights: list) -> list:
    """Разбить amount_cents пропорционально весам weights (list[int] >= 0, сумма > 0).

    Возвращает список из len(weights) целых цент-сумм, в сумме равный amount_cents.
    """
    if amount_cents < 0:
        raise ValueError("amount_cents must be >= 0")
    if not weights:
        raise ValueError("weights must not be empty")
    if any(w < 0 for w in weights):
        raise ValueError("weights must be >= 0")
    total_w = sum(weights)
    if total_w == 0:
        raise ValueError("weights sum must be > 0")

    exact = [amount_cents * w / total_w for w in weights]
    base = [int(math.floor(e)) for e in exact]
    rem = amount_cents - sum(base)
    # наибольшие дробные части получают по центу; при равенстве — раньше в списке
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - base[i]), i))
    for i in order[:rem]:
        base[i] += 1
    return base
