"""Баллы лояльности.

Правила (эталон):
- points_for_order: 1 балл за каждые ПОЛНОЕ число сотен центов в заказе;
  множитель по истории покупок: >= 100000 центов (1000.00) — x2,
  >= 500000 центов (5000.00) — x3 (проверяется от большего порога).
- expire_points: баллы живут 365 календарных дней со дня начисления,
  включительно; на день accrual + 365 балл ещё действует.
"""

from datetime import date, timedelta


def points_for_order(total_cents: int, history_cents: int = 0) -> int:
    """Начислить баллы за заказ total_cents с учётом истории history_cents."""
    if total_cents < 0:
        raise ValueError("total_cents must be >= 0")
    if history_cents < 0:
        raise ValueError("history_cents must be >= 0")
    base = total_cents // 100
    if history_cents >= 500000:
        multiplier = 3
    elif history_cents >= 100000:
        multiplier = 2
    else:
        multiplier = 1
    return base * multiplier


def expire_points(entries, on_date: date) -> int:
    """Суммировать действительные на on_date баллы.

    entries — список пар (ISO-дата начисления, количество баллов).
    """
    total = 0
    for iso, points in entries:
        accrued = date.fromisoformat(iso)
        if accrued <= on_date <= accrued + timedelta(days=364):
            total += points
    return total
