"""Исчерпывающий pytest-сьют для библиотеки ordercalc.

Покрывает discounts, split, loyalty: нормальные случаи, границы,
валидация входов (pytest.raises), параметризация, инварианты.
"""

from datetime import date, timedelta

import pytest

from ordercalc.discounts import TIERS, apply_tier_discount, bulk_discount_percent
from ordercalc.loyalty import expire_points, points_for_order
from ordercalc.split import split_payment, split_weighted


# ---------------------------------------------------------------------------
# discounts.apply_tier_discount
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("total_cents", "tier", "expected"),
    [
        (0, "bronze", 0),
        (123, "bronze", 123),          # 0% — без изменений
        (12345, "bronze", 12345),
        (100, "silver", 95),
        (589, "silver", 560),          # 559.55 -> 560 (обычное округление вверх)
        (205, "silver", 195),          # 194.75 -> 195
        (100, "gold", 90),
        (999, "gold", 899),            # 899.1 -> 899 (вниз)
        (1000, "platinum", 850),
        (9999, "platinum", 8499),      # 8499.15 -> 8499
        (9999, "bronze", 9999),
    ],
)
def test_apply_tier_discount_basic(total_cents, tier, expected):
    assert apply_tier_discount(total_cents, tier) == expected


@pytest.mark.parametrize(
    ("total_cents", "tier", "expected"),
    [
        # дробная часть ровно .5 — арифметическое half-up, а не banker's rounding
        (210, "silver", 200),    # 199.5 -> 200
        (25, "gold", 23),        # 22.5 -> 23 (half-even дал бы 22)
        (230, "platinum", 196),  # 195.5 -> 196
        (90, "gold", 81),        # 81.0 — целое
        (294, "silver", 279),    # 279.3 -> 279 (вниз)
        (6, "silver", 6),        # 5.7 -> 6
    ],
)
def test_apply_tier_discount_rounding_half_up(total_cents, tier, expected):
    from decimal import Decimal, ROUND_HALF_UP
    want = int(
        (Decimal(total_cents) * (Decimal(100 - TIERS[tier]) / Decimal(100)))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    assert want == expected  # защита от опечаток в самом тесте
    assert apply_tier_discount(total_cents, tier) == expected


def test_apply_tier_discount_all_tiers_covered():
    for tier, pct in TIERS.items():
        out = apply_tier_discount(10_000, tier)
        assert out == 10_000 - 10_000 * pct // 100  # на круглом числе точно
        assert 0 <= out <= 10_000


@pytest.mark.parametrize("total_cents", [-1, -100, -10**9])
def test_apply_tier_discount_negative_total(total_cents):
    with pytest.raises(ValueError, match="total_cents must be >= 0"):
        apply_tier_discount(total_cents, "gold")


@pytest.mark.parametrize(
    "tier",
    ["", "Bronze", "BRONZE", "silver ", "unknown", "diamond", "gold2", "123", None, 5],
)
def test_apply_tier_discount_unknown_tier(tier):
    with pytest.raises(ValueError, match="unknown tier"):
        apply_tier_discount(100, tier)


def test_apply_tier_discount_unknown_tier_message_contains_repr():
    with pytest.raises(ValueError) as excinfo:
        apply_tier_discount(100, "diamond")
    assert "diamond" in str(excinfo.value)


# ---------------------------------------------------------------------------
# discounts.bulk_discount_percent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("qty", "expected"),
    [
        (0, 0),
        (1, 0),
        (9, 0),
        (10, 3),    # граница «от 10» включительно
        (11, 3),
        (49, 3),
        (50, 7),    # граница «от 50» включительно
        (51, 7),
        (99, 7),
        (100, 12),  # граница «от 100» включительно
        (101, 12),
        (1000, 12),
    ],
)
def test_bulk_discount_percent_boundaries(qty, expected):
    assert bulk_discount_percent(qty) == expected


@pytest.mark.parametrize("qty", [-1, -10, -10**6])
def test_bulk_discount_percent_negative(qty):
    with pytest.raises(ValueError, match="qty must be >= 0"):
        bulk_discount_percent(qty)


# ---------------------------------------------------------------------------
# split.split_payment
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("amount_cents", "parts", "expected"),
    [
        (1, 1, [1]),
        (5, 1, [5]),
        (10, 5, [2, 2, 2, 2, 2]),        # остаток 0
        (10, 3, [4, 3, 3]),              # остаток 1 — первому
        (11, 4, [3, 3, 3, 2]),           # остаток 3 — первым трём
        (7, 7, [1] * 7),                 # amount == parts
        (100, 7, [15, 15, 14, 14, 14, 14, 14]),
        (1_000_000, 3, [333_334, 333_333, 333_333]),
    ],
)
def test_split_payment_basic(amount_cents, parts, expected):
    result = split_payment(amount_cents, parts)
    assert result == expected
    assert sum(result) == amount_cents
    assert len(result) == parts


@pytest.mark.parametrize(
    ("amount_cents", "parts"),
    [
        (-1, 1),
        (-100, 3),
        (10, 0),
        (10, -1),
        (10, -5),
        (0, 1),   # 0 < 1: не хватит по центу на часть
        (3, 5),
        (99, 100),
    ],
)
def test_split_payment_invalid(amount_cents, parts):
    with pytest.raises(ValueError):
        split_payment(amount_cents, parts)


def test_split_payment_error_messages():
    with pytest.raises(ValueError, match="amount_cents must be >= 0"):
        split_payment(-1, 2)
    with pytest.raises(ValueError, match="parts must be >= 1"):
        split_payment(10, 0)
    with pytest.raises(ValueError, match="less than number of parts"):
        split_payment(3, 5)


@pytest.mark.parametrize("parts", list(range(1, 13)))
def test_split_payment_invariant_sum(parts):
    amount = 100
    result = split_payment(amount, parts)
    assert sum(result) == amount
    assert len(result) == parts
    assert all(isinstance(x, int) for x in result)
    bases = set(result)
    assert max(bases) - min(bases) <= 1  # части отличаются максимум на 1 цент


# ---------------------------------------------------------------------------
# split.split_weighted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("amount_cents", "weights", "expected"),
    [
        (100, [1], [100]),
        (100, [2, 2], [50, 50]),                    # остаток 0
        (0, [5], [0]),                              # нулевая сумма допустима
        (101, [1, 2], [34, 67]),                    # наибольший остаток у первого
        (100, [1, 1, 1], [34, 33, 33]),             # равные дробные части — выигрывает ранний индекс
        (10, [1, 1, 1, 1], [3, 3, 2, 2]),           # rem=2 при полном равенстве
        (101, [0, 1, 1], [0, 51, 50]),              # нулевой вес не получает добор
        (100, [0, 100], [0, 100]),
        (100, [3, 3, 4], [30, 30, 40]),
        (1000, [1, 0, 3], [250, 0, 750]),
        (7, [1, 1, 1], [3, 2, 2]),
        (99, [50, 25, 25], [49, 25, 25]),           # точные 49.5/24.75/24.75, добор индексам 1 и 2
    ],
)
def test_split_weighted_basic(amount_cents, weights, expected):
    result = split_weighted(amount_cents, weights)
    assert result == expected
    assert sum(result) == amount_cents
    assert len(result) == len(weights)


@pytest.mark.parametrize(
    ("amount_cents", "weights", "message"),
    [
        (-1, [1], "amount_cents must be >= 0"),
        (-100, [1, 2], "amount_cents must be >= 0"),
        (100, [], "weights must not be empty"),
        (100, [1, -1], "weights must be >= 0"),
        (100, [-5, 10, 3], "weights must be >= 0"),
        (0, [0, 0], "weights sum must be > 0"),
        (100, [0, 0, 0], "weights sum must be > 0"),
    ],
)
def test_split_weighted_invalid(amount_cents, weights, message):
    with pytest.raises(ValueError, match=message):
        split_weighted(amount_cents, weights)


@pytest.mark.parametrize(
    ("amount_cents", "weights"),
    [
        (100, [1]),
        (100, [1, 1]),
        (100, [7, 3]),
        (101, [1, 2, 3]),
        (999, [10, 20, 30, 40]),
        (1, [1, 1, 1]),
        (0, [1, 2, 3]),
        (57, [0, 1, 0, 2]),
        (12345, [13, 17, 5, 65]),
        (3, [2, 2, 2, 2, 2]),
    ],
)
def test_split_weighted_invariants(amount_cents, weights):
    result = split_weighted(amount_cents, weights)
    assert len(result) == len(weights)
    assert sum(result) == amount_cents
    assert all(isinstance(x, int) for x in result)
    # нулевые веса не должны получать больше, чем пропорциональная доля округлённая вверх
    for got, w in zip(result, weights):
        if w == 0:
            assert got == 0
        else:
            assert got >= 0


def test_split_weighted_tie_goes_to_earlier_index():
    # 100 на [1,1]: точные 50.0/50.0 — остаток 0; проверяем стабильность
    assert split_weighted(100, [1, 1]) == [50, 50]
    # 5 на [1,1,1,1]: точные 1.25, остаток 1 — все равны, добор первому
    assert split_weighted(5, [1, 1, 1, 1]) == [2, 1, 1, 1]
    # 6 на [1,1,1,1]: остаток 2 — первым двум
    assert split_weighted(6, [1, 1, 1, 1]) == [2, 2, 1, 1]


def test_split_weighted_largest_remainder_wins():
    # 100 на [1, 2, 7]: точные 10 / 20 / 70 — остаток 0
    assert split_weighted(100, [1, 2, 7]) == [10, 20, 70]
    # 103 на [1, 2, 7]: точные 10.3 / 20.6 / 72.1, floor 10/20/72, остаток 1
    # наибольшая дробная часть у индекса 1 (0.6)
    assert split_weighted(103, [1, 2, 7]) == [10, 21, 72]


# ---------------------------------------------------------------------------
# loyalty.points_for_order
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("total_cents", "history_cents", "expected"),
    [
        (0, 0, 0),
        (99, 0, 0),                 # неполная сотня не считается
        (100, 0, 1),
        (199, 0, 1),
        (200, 0, 2),
        (12345, 0, 123),
        (100, None, 1),             # значение по умолчанию history_cents=0
        (100, 1, 1),
        (100, 99_999, 1),
        (100, 100_000, 2),          # порог x2 включительно
        (100, 100_001, 2),
        (100, 499_999, 2),
        (100, 500_000, 3),          # порог x3 включительно
        (100, 500_001, 3),
        (100, 10**9, 3),
        (250, 500_000, 6),          # 2 полных сотни * множитель 3
        (350, 100_000, 6),          # 3 * 2
    ],
)
def test_points_for_order(total_cents, history_cents, expected):
    if history_cents is None:
        assert points_for_order(total_cents) == expected
    else:
        assert points_for_order(total_cents, history_cents) == expected


@pytest.mark.parametrize(
    ("total_cents", "history_cents"),
    [
        (-1, 0),
        (-100, 100_000),
        (100, -1),
        (100, -100_000),
        (-1, -1),
    ],
)
def test_points_for_order_invalid(total_cents, history_cents):
    with pytest.raises(ValueError):
        points_for_order(total_cents, history_cents)


def test_points_for_order_error_messages():
    with pytest.raises(ValueError, match="total_cents must be >= 0"):
        points_for_order(-5, 0)
    with pytest.raises(ValueError, match="history_cents must be >= 0"):
        points_for_order(5, -5)


# ---------------------------------------------------------------------------
# loyalty.expire_points
# ---------------------------------------------------------------------------

ACCRUAL = date(2024, 1, 1)


@pytest.mark.parametrize(
    ("on_date", "expected"),
    [
        (date(2023, 12, 31), 0),        # день до начисления — не действует
        (date(2024, 1, 1), 10),         # день начисления — действует
        (date(2024, 6, 30), 10),        # середина окна
        (date(2024, 12, 30), 10),       # accrual + 364
        (date(2024, 12, 31), 10),       # accrual + 365 — ещё действует (включительно)
        (date(2025, 1, 1), 0),          # accrual + 366 — истёк
        (date(2030, 1, 1), 0),
    ],
)
def test_expire_points_window_boundaries(on_date, expected):
    entries = [("2024-01-01", 10)]
    assert expire_points(entries, on_date) == expected


def test_expire_points_sums_only_valid_entries():
    entries = [
        ("2024-01-01", 10),   # действует на 2024-05-01
        ("2024-04-01", 20),   # действует
        ("2024-05-02", 40),   # ещё не начислены на 2024-05-01
        ("2022-01-01", 80),   # давно истекли
    ]
    assert expire_points(entries, date(2024, 5, 1)) == 30


def test_expire_points_empty_entries():
    assert expire_points([], date(2024, 1, 1)) == 0


def test_expire_points_leap_year_window():
    # 2024-02-29 + 365 дней = 2025-02-28
    entries = [("2024-02-29", 5)]
    assert expire_points(entries, date(2025, 2, 28)) == 5
    assert expire_points(entries, date(2025, 3, 1)) == 0


def test_expire_points_zero_points_entry():
    entries = [("2024-03-01", 0)]
    assert expire_points(entries, date(2024, 3, 1)) == 0
    assert expire_points(entries, date(2025, 3, 2)) == 0


def test_expire_points_accepts_date_objects_and_isolation():
    on_date = date(2024, 2, 1)
    entries = [("2024-01-01", 1), ("2023-02-02", 2)]
    # проверяем, что функция не мутирует вход и работает с кортежами-парами
    snapshot = list(entries)
    expire_points(entries, on_date)
    assert entries == snapshot


def test_expire_points_exact_365_days_for_every_quarter():
    for month in (1, 4, 7, 10):
        accrual = date(2024, month, 15)
        entries = [(accrual.isoformat(), 7)]
        assert expire_points(entries, accrual + timedelta(days=365)) == 7
        assert expire_points(entries, accrual + timedelta(days=366)) == 0
        assert expire_points(entries, accrual - timedelta(days=1)) == 0


# ---------------------------------------------------------------------------
# package-level
# ---------------------------------------------------------------------------

def test_package_exposes_modules():
    import ordercalc

    assert set(ordercalc.__all__) == {"discounts", "split", "loyalty"}
    for name in ordercalc.__all__:
        assert hasattr(ordercalc, name)


def test_tiers_reference():
    assert TIERS == {"bronze": 0, "silver": 5, "gold": 10, "platinum": 15}
