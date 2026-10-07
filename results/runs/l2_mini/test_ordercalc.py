"""Автотесты для учебной библиотеки ordercalc (pytest + stdlib)."""

from datetime import date

import pytest

from ordercalc.discounts import TIERS, apply_tier_discount, bulk_discount_percent
from ordercalc.loyalty import expire_points, points_for_order
from ordercalc.split import split_payment, split_weighted


# =============================================================== discounts.py


class TestApplyTierDiscount:
    @pytest.mark.parametrize("tier,expected_pct", sorted(TIERS.items()))
    def test_zero_amount_is_zero_for_every_tier(self, tier, expected_pct):
        assert apply_tier_discount(0, tier) == 0

    @pytest.mark.parametrize("tier,pct", sorted(TIERS.items()))
    def test_thousand_cents_matches_tier_percent(self, tier, pct):
        assert apply_tier_discount(1000, tier) == 1000 - pct * 10

    @pytest.mark.parametrize(
        "total_cents,tier,expected",
        [
            (12345, "bronze", 12345),
            (0, "bronze", 0),
            (100, "silver", 95),
            (200, "silver", 190),
            (999999, "silver", 949999),
            (100, "gold", 90),
            (123456789, "gold", 111111110),
            (1000, "platinum", 850),
            (20, "platinum", 17),
        ],
    )
    def test_typical_values(self, total_cents, tier, expected):
        assert apply_tier_discount(total_cents, tier) == expected

    @pytest.mark.parametrize(
        "total_cents,tier,expected",
        [
            # дробная часть ровно 0.5 — арифметическое округление вверх
            (10, "silver", 10),    # 9.50 -> 10
            (30, "silver", 29),    # 28.50 -> 29
            (50, "silver", 48),    # 47.50 -> 48
            (5, "gold", 5),        # 4.50 -> 5
            (25, "gold", 23),      # 22.50 -> 23
            (105, "gold", 95),     # 94.50 -> 95
            (10, "platinum", 9),   # 8.50 -> 9
            (30, "platinum", 26),  # 25.50 -> 26
            # дробная часть < 0.5 — округление вниз
            (21, "gold", 19),      # 18.9 -> 19
            (33, "silver", 31),    # 31.35 -> 31
            (99, "gold", 89),      # 89.1 -> 89
        ],
    )
    def test_half_up_rounding(self, total_cents, tier, expected):
        assert apply_tier_discount(total_cents, tier) == expected

    @pytest.mark.parametrize("total_cents", [-1, -100, -10**9])
    def test_negative_amount_raises(self, total_cents):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            apply_tier_discount(total_cents, "gold")

    @pytest.mark.parametrize("tier", ["diamond", "", "GOLD", "Silver", "bronze ", None])
    def test_unknown_tier_raises(self, tier):
        with pytest.raises(ValueError, match="unknown tier"):
            apply_tier_discount(1000, tier)

    def test_negative_amount_checked_before_tier(self):
        # сумма проверяется раньше уровня
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            apply_tier_discount(-1, "no-such-tier")

    @pytest.mark.parametrize("total_cents,tier", [(0, "bronze"), (123, "gold")])
    def test_result_is_int(self, total_cents, tier):
        assert isinstance(apply_tier_discount(total_cents, tier), int)


class TestBulkDiscountPercent:
    @pytest.mark.parametrize(
        "qty,expected",
        [
            (0, 0),
            (1, 0),
            (5, 0),
            (9, 0),      # последняя величина без скидки
            (10, 3),     # граница «от 10 шт.» включительно
            (11, 3),
            (25, 3),
            (49, 3),     # последняя величина с 3%
            (50, 7),     # граница «от 50 шт.» включительно
            (51, 7),
            (75, 7),
            (99, 7),     # последняя величина с 7%
            (100, 12),   # граница «от 100 шт.» включительно
            (101, 12),
            (250, 12),
            (10**6, 12),
        ],
    )
    def test_thresholds_are_inclusive(self, qty, expected):
        assert bulk_discount_percent(qty) == expected

    @pytest.mark.parametrize("qty", [-1, -10, -10**6])
    def test_negative_qty_raises(self, qty):
        with pytest.raises(ValueError, match="qty must be >= 0"):
            bulk_discount_percent(qty)

    def test_result_is_int(self):
        assert isinstance(bulk_discount_percent(42), int)


# ================================================================ loyalty.py


class TestPointsForOrder:
    @pytest.mark.parametrize(
        "total_cents,history_cents,expected",
        [
            (0, 0, 0),
            (99, 0, 0),            # неполная сотня не считается
            (100, 0, 1),
            (199, 0, 1),
            (200, 0, 2),
            (12345, 0, 123),
            # границы множителей по истории
            (10000, 99999, 100),   # x1
            (10000, 100000, 200),  # x2 от 100000 центов
            (10000, 100001, 200),
            (10000, 499999, 200),
            (10000, 500000, 300),  # x3 от 500000 центов
            (10000, 500001, 300),
            (10000, 10**9, 300),
            (0, 500000, 0),
        ],
    )
    def test_points_and_multipliers(self, total_cents, history_cents, expected):
        assert points_for_order(total_cents, history_cents) == expected

    def test_default_history_is_zero(self):
        assert points_for_order(10000) == 100
        assert points_for_order(10000, 0) == 100

    @pytest.mark.parametrize("total_cents", [-1, -100])
    def test_negative_total_raises(self, total_cents):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            points_for_order(total_cents, 0)

    @pytest.mark.parametrize("history_cents", [-1, -100])
    def test_negative_history_raises(self, history_cents):
        with pytest.raises(ValueError, match="history_cents must be >= 0"):
            points_for_order(100, history_cents)

    def test_negative_total_checked_before_history(self):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            points_for_order(-1, -1)


class TestExpirePoints:
    def test_empty_entries(self):
        assert expire_points([], date(2024, 6, 1)) == 0

    @pytest.mark.parametrize(
        "on_date,expected",
        [
            (date(2023, 12, 31), 0),   # день до начисления
            (date(2024, 1, 1), 100),   # день начисления
            (date(2024, 7, 1), 100),
            (date(2024, 12, 30), 100),  # +364 дня
            (date(2024, 12, 31), 100),  # +365 дней — ещё действует
            (date(2025, 1, 1), 0),      # +366 дней — истёк
            (date(2030, 1, 1), 0),
        ],
    )
    def test_single_entry_boundaries(self, on_date, expected):
        assert expire_points([("2024-01-01", 100)], on_date) == expected

    @pytest.mark.parametrize(
        "on_date,expected",
        [
            (date(2023, 2, 28), 0),   # день до начисления
            (date(2023, 3, 1), 50),   # день начисления
            (date(2024, 2, 28), 50),
            (date(2024, 2, 29), 50),  # accrual + 365 — 29 февраля
            (date(2024, 3, 1), 0),    # +366 дней — истёк
        ],
    )
    def test_leap_year_boundary(self, on_date, expected):
        # 2023-03-01 + 365 дней = 2024-02-29 (високосный 2024)
        assert expire_points([("2023-03-01", 50)], on_date) == expected

    @pytest.mark.parametrize(
        "on_date,expected",
        [
            (date(2024, 2, 29), 7),   # день начисления (високосный день)
            (date(2025, 2, 27), 7),
            (date(2025, 2, 28), 7),   # 2024-02-29 + 365 = 2025-02-28 — ещё действует
            (date(2025, 3, 1), 0),    # истёк
        ],
    )
    def test_accrual_on_leap_day(self, on_date, expected):
        assert expire_points([("2024-02-29", 7)], on_date) == expected

    def test_mixed_entries(self):
        entries = [
            ("2024-01-01", 10),
            ("2024-06-01", 20),
            ("2020-01-01", 100),  # давно истёк
            ("2025-06-01", 5),    # начисление в будущем относительно части дат
        ]
        assert expire_points(entries, date(2024, 7, 1)) == 30
        assert expire_points(entries, date(2024, 1, 1)) == 10
        assert expire_points(entries, date(2026, 1, 1)) == 5
        assert expire_points(entries, date(2019, 1, 1)) == 0

    def test_entries_as_inner_lists(self):
        # распаковка работает и для пар-списков
        assert expire_points([["2024-01-01", 100]], date(2024, 5, 1)) == 100


# ================================================================== split.py


class TestSplitPayment:
    @pytest.mark.parametrize(
        "amount,parts,expected",
        [
            (1, 1, [1]),
            (7, 1, [7]),
            (5, 5, [1, 1, 1, 1, 1]),
            (3, 2, [2, 1]),
            (10, 7, [2, 2, 2, 1, 1, 1, 1]),
            (100, 3, [34, 33, 33]),
            (100, 4, [25, 25, 25, 25]),
            (
                1000000,
                7,
                [142858, 142857, 142857, 142857, 142857, 142857, 142857],
            ),
        ],
    )
    def test_values(self, amount, parts, expected):
        assert split_payment(amount, parts) == expected

    @pytest.mark.parametrize(
        "amount,parts", [(10, 1), (100, 3), (7, 4), (1000000, 7)]
    )
    def test_invariants(self, amount, parts):
        result = split_payment(amount, parts)
        assert sum(result) == amount
        assert len(result) == parts
        assert all(isinstance(x, int) for x in result)
        assert max(result) - min(result) <= 1
        assert min(result) >= 1

    @pytest.mark.parametrize("amount", [-1, -100])
    def test_negative_amount_raises(self, amount):
        with pytest.raises(ValueError, match="amount_cents must be >= 0"):
            split_payment(amount, 3)

    @pytest.mark.parametrize("parts", [0, -1, -10])
    def test_invalid_parts_raises(self, parts):
        with pytest.raises(ValueError, match="parts must be >= 1"):
            split_payment(10, parts)

    @pytest.mark.parametrize("amount,parts", [(4, 5), (0, 1), (0, 3), (99, 100)])
    def test_amount_less_than_parts_raises(self, amount, parts):
        with pytest.raises(
            ValueError, match="amount_cents is less than number of parts"
        ):
            split_payment(amount, parts)

    def test_amount_checked_before_parts(self):
        with pytest.raises(ValueError, match="amount_cents must be >= 0"):
            split_payment(-1, 0)


class TestSplitWeighted:
    @pytest.mark.parametrize(
        "amount,weights,expected",
        [
            (123, [5], [123]),
            (100, [1, 1], [50, 50]),
            (100, [2, 3], [40, 60]),
            (1000, [3, 7], [300, 700]),
            (100, [0, 1], [0, 100]),
            (99, [1, 1, 1], [33, 33, 33]),
            (5, [1, 1, 1, 1, 1], [1, 1, 1, 1, 1]),
            (100, [1, 2], [33, 67]),  # floor [33, 66], цент части с весом 2
            (10, [1, 2], [3, 7]),
            (0, [1, 2], [0, 0]),
        ],
    )
    def test_exact_and_basic_rounding(self, amount, weights, expected):
        assert split_weighted(amount, weights) == expected

    @pytest.mark.parametrize(
        "amount,weights,expected",
        [
            # при равных дробных частях цент получает более ранний индекс
            (10, [1, 1, 1], [4, 3, 3]),
            (101, [1, 1, 1], [34, 34, 33]),
            (7, [1, 1, 1], [3, 2, 2]),
            (3, [1, 1], [2, 1]),
            (6, [1, 1, 1, 1], [2, 2, 1, 1]),
        ],
    )
    def test_largest_remainder_tie_breaks_by_index(
        self, amount, weights, expected
    ):
        assert split_weighted(amount, weights) == expected

    @pytest.mark.parametrize(
        "amount,weights",
        [(100, [1, 2]), (101, [1, 1, 1]), (7, [3, 5, 2]), (99, [1, 1, 1])],
    )
    def test_invariants(self, amount, weights):
        result = split_weighted(amount, weights)
        assert sum(result) == amount
        assert len(result) == len(weights)
        assert all(isinstance(x, int) for x in result)
        assert all(x >= 0 for x in result)

    @pytest.mark.parametrize("amount", [-1, -100])
    def test_negative_amount_raises(self, amount):
        with pytest.raises(ValueError, match="amount_cents must be >= 0"):
            split_weighted(amount, [1, 1])

    def test_empty_weights_raises(self):
        with pytest.raises(ValueError, match="weights must not be empty"):
            split_weighted(10, [])

    @pytest.mark.parametrize("weights", [[-1, 2], [1, -1], [-5]])
    def test_negative_weight_raises(self, weights):
        with pytest.raises(ValueError, match="weights must be >= 0"):
            split_weighted(10, weights)

    @pytest.mark.parametrize("weights", [[0], [0, 0, 0]])
    def test_zero_sum_weights_raises(self, weights):
        with pytest.raises(ValueError, match="weights sum must be > 0"):
            split_weighted(10, weights)

    def test_amount_checked_before_weights(self):
        with pytest.raises(ValueError, match="amount_cents must be >= 0"):
            split_weighted(-1, [])
