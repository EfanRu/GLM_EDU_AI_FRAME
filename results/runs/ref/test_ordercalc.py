"""Эталонный тест-сьют (REF): написан вручную опытным разработчиком.

Калибровочная планка для сравнения с AI-подходами. Цель — 100% line/branch
покрытия ordercalc и ловля всех посеянных регрессий.
"""

from datetime import date

import pytest

from ordercalc.discounts import apply_tier_discount, bulk_discount_percent, TIERS
from ordercalc.loyalty import expire_points, points_for_order
from ordercalc.split import split_payment, split_weighted


# ---------------- discounts.apply_tier_discount ----------------

@pytest.mark.parametrize("total_cents,tier,expected", [
    (1000, "bronze", 1000),     # 0% — отсутствие скидки
    (1000, "silver", 950),
    (1000, "gold", 900),
    (200, "platinum", 170),
    (0, "gold", 0),             # нулевая сумма валидна
    (310, "silver", 295),       # 294.5 -> 295: округление half-up
    (630, "silver", 599),       # 598.5 -> 599: half-up на нечётной границе
    (290, "silver", 276),       # 275.5 -> 276
    (999, "gold", 899),         # 899.1 -> 899 (дробь < 0.5)
])
def test_apply_tier_discount_values(total_cents, tier, expected):
    assert apply_tier_discount(total_cents, tier) == expected


@pytest.mark.parametrize("total_cents,tier", [
    (-1, "gold"), (-100, "bronze"),
])
def test_apply_tier_discount_negative_total(total_cents, tier):
    with pytest.raises(ValueError):
        apply_tier_discount(total_cents, tier)


@pytest.mark.parametrize("tier", ["", "GOLD", "silver ", "diamond", None])
def test_apply_tier_discount_unknown_tier(tier):
    with pytest.raises(ValueError):
        apply_tier_discount(1000, tier)


def test_tiers_table():
    assert set(TIERS) == {"bronze", "silver", "gold", "platinum"}


# ---------------- discounts.bulk_discount_percent ----------------

@pytest.mark.parametrize("qty,expected", [
    (0, 0), (1, 0), (9, 0),      # до порога
    (10, 3), (49, 3),            # первый порог, граница включительно
    (50, 7), (99, 7),            # второй порог
    (100, 12),                   # третий порог, граница ровно 100
    (101, 12), (10_000, 12),
])
def test_bulk_discount_percent(qty, expected):
    assert bulk_discount_percent(qty) == expected


def test_bulk_discount_percent_negative():
    with pytest.raises(ValueError):
        bulk_discount_percent(-1)


# ---------------- split.split_payment ----------------

def test_split_payment_basic():
    assert split_payment(100, 4) == [25, 25, 25, 25]


def test_split_payment_remainder_to_first_parts():
    # 105/2 = 52.5 -> остаток 1 цент первой части
    assert split_payment(105, 2) == [53, 52]
    assert split_payment(10, 3) == [4, 3, 3]
    assert split_payment(7, 7) == [1] * 7


def test_split_payment_sum_preserved():
    for amount, parts in [(105, 2), (999, 7), (1, 1), (12345, 11)]:
        result = split_payment(amount, parts)
        assert sum(result) == amount
        assert len(result) == parts
        assert all(v >= 1 for v in result)
        # части отличаются не более чем на 1 цент
        assert max(result) - min(result) <= 1


@pytest.mark.parametrize("amount,parts", [
    (-100, 3),   # отрицательная сумма
    (100, 0),    # ноль частей
    (100, -2),   # отрицательное число частей
    (2, 3),      # суммы не хватает по центу на часть
])
def test_split_payment_invalid(amount, parts):
    with pytest.raises(ValueError):
        split_payment(amount, parts)


# ---------------- split.split_weighted ----------------

def test_split_weighted_exact():
    assert split_weighted(100, [1, 1, 2]) == [25, 25, 50]


def test_split_weighted_remainder_largest_fraction():
    # 100 на [1, 2, 3] = 16.67/33.33/50 -> [16, 33, 50] + 1 цент части с дробью .67... (второй)
    assert split_weighted(100, [1, 2, 3]) == [17, 33, 50]


def test_split_weighted_tie_earlier_index_wins():
    # 101 на [1, 1]: обе дроби по 0.5, цент получает первая часть
    assert split_weighted(101, [1, 1]) == [51, 50]


def test_split_weighted_zero_weight_part():
    # часть с нулевым весом получает 0
    assert split_weighted(100, [1, 0]) == [100, 0]


def test_split_weighted_sum_preserved():
    for amount, weights in [(101, [1, 1, 1]), (997, [7, 3, 5, 1]), (50, [2, 2, 1])]:
        result = split_weighted(amount, weights)
        assert sum(result) == amount
        assert len(result) == len(weights)


@pytest.mark.parametrize("amount,weights", [
    (-5, [1, 1]),      # отрицательная сумма
    (100, []),         # пустые веса
    (100, [1, -1]),    # отрицательный вес
    (100, [0, 0]),     # сумма весов 0
])
def test_split_weighted_invalid(amount, weights):
    with pytest.raises(ValueError):
        split_weighted(amount, weights)


# ---------------- loyalty.points_for_order ----------------

@pytest.mark.parametrize("total_cents,history_cents,expected", [
    (10_000, 0, 100),          # x1, без истории
    (9_999, 500_000, 297),     # только полные сотни, множитель x3 всё равно применяется
    (10_000, 99_999, 100),     # история не дотянула до x2
    (10_000, 100_000, 200),    # ровно порог x2
    (10_000, 499_999, 200),    # внутри x2
    (10_000, 500_000, 300),    # ровно порог x3
    (10_000, 1_000_000, 300),  # выше x3
    (0, 0, 0),
])
def test_points_for_order(total_cents, history_cents, expected):
    assert points_for_order(total_cents, history_cents) == expected


@pytest.mark.parametrize("total,history", [(-1, 0), (0, -1)])
def test_points_for_order_invalid(total, history):
    with pytest.raises(ValueError):
        points_for_order(total, history)


# ---------------- loyalty.expire_points ----------------

def test_expire_points_active_window():
    entries = [("2024-01-01", 10), ("2024-06-15", 20)]
    assert expire_points(entries, date(2024, 6, 16)) == 30


def test_expire_points_last_day_is_valid():
    # день начисления + 365 включительно
    assert expire_points([("2024-02-29", 5)], date(2025, 2, 28)) == 5  # високосный год
    assert expire_points([("2024-01-01", 5)], date(2024, 12, 31)) == 5


def test_expire_points_expired():
    assert expire_points([("2024-01-01", 5)], date(2025, 1, 1)) == 0  # 366-й день
    assert expire_points([("2023-05-05", 7)], date(2024, 12, 1)) == 0


def test_expire_points_not_yet_accrued():
    # балл, начисленный «в будущем» относительно on_date, не учитывается
    assert expire_points([("2025-01-01", 5)], date(2024, 12, 31)) == 0


def test_expire_points_day_of_accrual():
    assert expire_points([("2024-03-10", 8)], date(2024, 3, 10)) == 8


def test_expire_points_empty():
    assert expire_points([], date(2024, 1, 1)) == 0
