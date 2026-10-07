"""Тесты для учебной библиотеки ordercalc (pytest + стандартная библиотека)."""

from datetime import date, timedelta

import pytest

from ordercalc.discounts import TIERS, apply_tier_discount, bulk_discount_percent
from ordercalc.loyalty import expire_points, points_for_order
from ordercalc.split import split_payment, split_weighted


# ---------------------------------------------------------------------------
# ordercalc.discounts
# ---------------------------------------------------------------------------

class TestTiersConstant:
    def test_tiers_mapping(self):
        assert TIERS == {"bronze": 0, "silver": 5, "gold": 10, "platinum": 15}


class TestApplyTierDiscount:
    @pytest.mark.parametrize(
        "total_cents, tier, expected",
        [
            (0, "bronze", 0),
            (1, "bronze", 1),
            (100, "bronze", 100),
            (9999, "bronze", 9999),
            (1000, "silver", 950),
            (1000, "gold", 900),
            (1000, "platinum", 850),
            (999, "silver", 949),          # 949.05 -> 949
            (2946, "platinum", 2504),      # 2504.1 -> 2504
            (1, "silver", 1),              # 0.95 -> 1
            (1, "gold", 1),                # 0.9 -> 1
            (1, "platinum", 1),            # 0.85 -> 1
            (2, "silver", 2),              # 1.9 -> 2
            (0, "platinum", 0),
            (10**9, "gold", 900_000_000),
        ],
    )
    def test_typical_values(self, total_cents, tier, expected):
        assert apply_tier_discount(total_cents, tier) == expected

    @pytest.mark.parametrize("total_cents", [0, 1, 7, 100, 12345, 10**7])
    def test_bronze_keeps_amount_unchanged(self, total_cents):
        assert apply_tier_discount(total_cents, "bronze") == total_cents

    @pytest.mark.parametrize(
        "total_cents, tier, expected",
        [
            # silver: total * 0.95 даёт ровно *.5
            (10, "silver", 10),      # 9.5 -> 10
            (110, "silver", 105),    # 104.5 -> 105
            (210, "silver", 200),    # 199.5 -> 200
            (310, "silver", 295),    # 294.5 -> 295 (half-up, а не банковское)
            (630, "silver", 599),    # 598.5 -> 599
            # gold: total * 0.90 даёт ровно *.5
            (5, "gold", 5),          # 4.5 -> 5
            (15, "gold", 14),        # 13.5 -> 14
            (25, "gold", 23),        # 22.5 -> 23
            (35, "gold", 32),        # 31.5 -> 32
            # platinum: total * 0.85 даёт ровно *.5
            (10, "platinum", 9),     # 8.5 -> 9
            (30, "platinum", 26),    # 25.5 -> 26
            (50, "platinum", 43),    # 42.5 -> 43
        ],
    )
    def test_half_up_rounding_on_boundary(self, total_cents, tier, expected):
        assert apply_tier_discount(total_cents, tier) == expected

    @pytest.mark.parametrize("tier", list(TIERS))
    def test_negative_total_raises_for_every_tier(self, tier):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            apply_tier_discount(-1, tier)

    @pytest.mark.parametrize("total_cents", [-1, -100, -10**6])
    def test_negative_total_message(self, total_cents):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            apply_tier_discount(total_cents, "bronze")

    @pytest.mark.parametrize(
        "tier", ["", "Silver", "GOLD", "silver ", "diamond", "unknown", None, 42]
    )
    def test_unknown_tier_raises(self, tier):
        with pytest.raises(ValueError, match="unknown tier"):
            apply_tier_discount(1000, tier)

    @pytest.mark.parametrize("tier", list(TIERS))
    def test_result_is_int_within_bounds(self, tier):
        result = apply_tier_discount(4242, tier)
        assert isinstance(result, int)
        assert 0 <= result <= 4242


class TestBulkDiscountPercent:
    @pytest.mark.parametrize(
        "qty, expected",
        [
            (0, 0),
            (1, 0),
            (5, 0),
            (9, 0),
            (10, 3),
            (11, 3),
            (25, 3),
            (49, 3),
            (50, 7),
            (51, 7),
            (75, 7),
            (99, 7),
            (100, 12),
            (101, 12),
            (500, 12),
            (10000, 12),
        ],
    )
    def test_thresholds_are_inclusive(self, qty, expected):
        assert bulk_discount_percent(qty) == expected

    @pytest.mark.parametrize("qty", [-1, -10, -10**6])
    def test_negative_qty_raises(self, qty):
        with pytest.raises(ValueError, match="qty must be >= 0"):
            bulk_discount_percent(qty)


# ---------------------------------------------------------------------------
# ordercalc.loyalty
# ---------------------------------------------------------------------------

class TestPointsForOrder:
    @pytest.mark.parametrize(
        "total_cents, expected",
        [
            (0, 0),
            (1, 0),
            (99, 0),
            (100, 1),
            (101, 1),
            (199, 1),
            (200, 2),
            (12345, 123),
            (99999, 999),
            (1_000_000, 10_000),
        ],
    )
    def test_base_points_full_hundreds_only(self, total_cents, expected):
        assert points_for_order(total_cents) == expected

    @pytest.mark.parametrize(
        "history_cents, multiplier",
        [
            (0, 1),
            (1, 1),
            (99_999, 1),
            (100_000, 2),
            (100_001, 2),
            (499_999, 2),
            (500_000, 3),
            (500_001, 3),
            (5_000_000, 3),
        ],
    )
    def test_history_multiplier_thresholds(self, history_cents, multiplier):
        assert points_for_order(10_000, history_cents) == 100 * multiplier

    def test_default_history_is_zero(self):
        assert points_for_order(500) == points_for_order(500, 0) == 5

    @pytest.mark.parametrize("total_cents", [-1, -100])
    def test_negative_total_raises(self, total_cents):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            points_for_order(total_cents, 0)

    def test_negative_history_raises(self):
        with pytest.raises(ValueError, match="history_cents must be >= 0"):
            points_for_order(100, -1)


class TestExpirePoints:
    def test_empty_entries(self):
        assert expire_points([], date(2024, 5, 1)) == 0

    def test_on_accrual_date_still_valid(self):
        assert expire_points([("2024-05-01", 10)], date(2024, 5, 1)) == 10

    def test_before_accrual_not_counted(self):
        assert expire_points([("2024-05-01", 10)], date(2024, 4, 30)) == 0

    def test_exactly_365_days_still_valid(self):
        accrual = date(2024, 5, 1)
        assert expire_points([("2024-05-01", 10)], accrual + timedelta(days=365)) == 10

    def test_366_days_expired(self):
        accrual = date(2024, 5, 1)
        assert expire_points([("2024-05-01", 10)], accrual + timedelta(days=366)) == 0

    @pytest.mark.parametrize(
        "accrual_iso, last_valid_iso",
        [
            ("2023-01-01", "2024-01-01"),   # обычный год: ровно 365 дней
            ("2024-01-01", "2024-12-31"),   # високосный 2024 внутри интервала
            ("2023-03-01", "2024-02-29"),   # интервал захватывает 29.02.2024
            ("2024-02-29", "2025-02-28"),   # начисление в високосный день
            ("2020-02-28", "2021-02-27"),   # день перед 29.02 в високосном году
        ],
    )
    def test_last_valid_day_and_first_expired_day(self, accrual_iso, last_valid_iso):
        points = 7
        last_valid = date.fromisoformat(last_valid_iso)
        assert expire_points([(accrual_iso, points)], last_valid) == points
        assert expire_points([(accrual_iso, points)], last_valid + timedelta(days=1)) == 0

    def test_mixed_entries_sum_only_valid(self):
        entries = [
            ("2020-01-01", 10),   # истёк к 2024-06-15
            ("2024-01-01", 20),   # действует
            ("2024-06-15", 40),   # начислен в саму дату проверки
            ("2024-12-31", 80),   # ещё не начислен
        ]
        assert expire_points(entries, date(2024, 6, 15)) == 60

    def test_zero_points_entry(self):
        assert expire_points([("2024-01-01", 0)], date(2024, 6, 1)) == 0

    def test_entries_as_lists(self):
        assert expire_points([["2024-01-01", 5]], date(2024, 6, 1)) == 5

    @pytest.mark.parametrize("bad_iso", ["2024-13-01", "2024-02-30", "not-a-date", ""])
    def test_invalid_iso_date_raises(self, bad_iso):
        with pytest.raises(ValueError):
            expire_points([(bad_iso, 10)], date(2024, 6, 1))


# ---------------------------------------------------------------------------
# ordercalc.split
# ---------------------------------------------------------------------------

class TestSplitPayment:
    @pytest.mark.parametrize(
        "amount_cents, parts, expected",
        [
            (0, 1, [0]),
            (1, 1, [1]),
            (5, 5, [1, 1, 1, 1, 1]),
            (7, 3, [3, 2, 2]),
            (10, 2, [5, 5]),
            (12, 5, [3, 3, 2, 2, 2]),
            (100, 4, [25, 25, 25, 25]),
            (101, 4, [26, 25, 25, 25]),
            (1000, 3, [334, 333, 333]),
            (99, 2, [50, 49]),
        ],
    )
    def test_split_values_and_remainder_distribution(self, amount_cents, parts, expected):
        assert split_payment(amount_cents, parts) == expected

    @pytest.mark.parametrize(
        "amount_cents, parts",
        [(100, 4), (101, 4), (7, 3), (12, 5), (999, 7), (100000, 13)],
    )
    def test_invariants(self, amount_cents, parts):
        result = split_payment(amount_cents, parts)
        assert isinstance(result, list)
        assert len(result) == parts
        assert sum(result) == amount_cents
        assert all(isinstance(p, int) for p in result)
        assert all(p >= 0 for p in result)
        assert max(result) - min(result) <= 1

    @pytest.mark.parametrize("amount_cents", [-1, -100])
    def test_negative_amount_raises(self, amount_cents):
        with pytest.raises(ValueError, match="amount_cents must be >= 0"):
            split_payment(amount_cents, 3)

    @pytest.mark.parametrize("parts", [0, -1, -10])
    def test_invalid_parts_raises(self, parts):
        with pytest.raises(ValueError, match="parts must be >= 1"):
            split_payment(100, parts)

    @pytest.mark.parametrize("amount_cents, parts", [(3, 5), (0, 3), (99, 100)])
    def test_amount_less_than_parts_raises(self, amount_cents, parts):
        with pytest.raises(
            ValueError, match="amount_cents is less than number of parts"
        ):
            split_payment(amount_cents, parts)


class TestSplitWeighted:
    @pytest.mark.parametrize(
        "amount_cents, weights, expected",
        [
            (0, [1], [0]),
            (0, [3, 7], [0, 0]),
            (100, [1, 1], [50, 50]),
            (90, [1, 2], [30, 60]),
            (100, [1, 2], [33, 67]),
            (100, [2, 3], [40, 60]),
            (100, [1, 1, 2], [25, 25, 50]),
            (7, [1, 1, 5], [1, 1, 5]),
            (100, [0, 1], [0, 100]),
            (100, [0, 0, 1], [0, 0, 100]),
            (100, [1, 1, 1], [34, 33, 33]),  # равные дробные части -> раньше в списке
            (101, [1, 1], [51, 50]),         # 50.5/50.5 -> первый получает лишний цент
            (10, [1, 1, 1], [4, 3, 3]),
            (2, [1, 1, 1], [1, 1, 0]),
            (1, [1, 1], [1, 0]),
            (5, [1, 1, 0], [3, 2, 0]),
        ],
    )
    def test_split_values(self, amount_cents, weights, expected):
        assert split_weighted(amount_cents, weights) == expected

    @pytest.mark.parametrize(
        "amount_cents, weights",
        [
            (100, [1, 2, 7]),
            (999, [3, 3, 3]),
            (12345, [2, 5, 11, 13]),
            (1, [1, 1, 1, 1, 1]),
            (50, [0, 1, 0]),
            (10**6, [7, 11, 13, 17]),
        ],
    )
    def test_invariants(self, amount_cents, weights):
        result = split_weighted(amount_cents, weights)
        assert isinstance(result, list)
        assert len(result) == len(weights)
        assert sum(result) == amount_cents
        assert all(isinstance(p, int) for p in result)
        assert all(p >= 0 for p in result)
        # нулевой вес никогда не получает центов (метод наибольших остатков)
        for weight, part in zip(weights, result):
            if weight == 0:
                assert part == 0

    @pytest.mark.parametrize(
        "amount_cents, n",
        [(10, 3), (100, 3), (101, 4), (37, 5), (1000, 7)],
    )
    def test_equal_weights_match_even_split(self, amount_cents, n):
        result = split_weighted(amount_cents, [1] * n)
        base, rem = divmod(amount_cents, n)
        assert result == [base + 1] * rem + [base] * (n - rem)
        assert max(result) - min(result) <= 1

    @pytest.mark.parametrize("amount_cents", [-1, -100])
    def test_negative_amount_raises(self, amount_cents):
        with pytest.raises(ValueError, match="amount_cents must be >= 0"):
            split_weighted(amount_cents, [1, 2])

    def test_empty_weights_raises(self):
        with pytest.raises(ValueError, match="weights must not be empty"):
            split_weighted(100, [])

    @pytest.mark.parametrize("weights", [[-1], [1, -2, 3], [0, -5]])
    def test_negative_weight_raises(self, weights):
        with pytest.raises(ValueError, match="weights must be >= 0"):
            split_weighted(100, weights)

    @pytest.mark.parametrize("weights", [[0], [0, 0], [0, 0, 0]])
    def test_all_zero_weights_raises(self, weights):
        with pytest.raises(ValueError, match="weights sum must be > 0"):
            split_weighted(100, weights)
