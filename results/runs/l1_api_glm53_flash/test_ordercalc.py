from datetime import date

import pytest

from ordercalc.discounts import TIERS, apply_tier_discount, bulk_discount_percent
from ordercalc.loyalty import expire_points, points_for_order
from ordercalc.split import split_payment, split_weighted


# ---------------------------------------------------------------------------
# ordercalc.discounts.apply_tier_discount
# ---------------------------------------------------------------------------

class TestApplyTierDiscount:

    @pytest.mark.parametrize(
        ("total_cents", "tier", "expected"),
        [
            (0, "bronze", 0),
            (0, "silver", 0),
            (0, "gold", 0),
            (0, "platinum", 0),
            (1000, "bronze", 1000),
            (1000, "silver", 950),
            (1000, "gold", 900),
            (1000, "platinum", 850),
            (12345, "bronze", 12345),
            (1, "silver", 1),       # 0.95 -> 1 (half-up)
            (2, "silver", 2),       # 1.90 -> 2
            (12, "silver", 11),     # 11.40 -> 11 (вниз)
            (310, "silver", 295),   # 294.50 -> 295 (эталон half-up)
            (5, "gold", 5),         # 4.50 -> 5
            (6, "gold", 5),         # 5.40 -> 5
            (15, "gold", 14),       # 13.50 -> 14
            (4, "platinum", 3),     # 3.40 -> 3
            (7, "platinum", 6),     # 5.95 -> 6
            (35, "platinum", 30),   # 29.75 -> 30
            (123456789, "platinum", 104938271),  # 104938270.65 -> 104938271
        ],
    )
    def test_values(self, total_cents, tier, expected):
        assert apply_tier_discount(total_cents, tier) == expected

    @pytest.mark.parametrize(("tier", "pct"), sorted(TIERS.items()))
    def test_matches_tier_table(self, tier, pct):
        assert apply_tier_discount(10000, tier) == 10000 - 100 * pct

    @pytest.mark.parametrize("tier", ["bronze", "silver", "gold", "platinum"])
    def test_returns_int(self, tier):
        assert isinstance(apply_tier_discount(999, tier), int)

    def test_tiers_table(self):
        assert TIERS == {"bronze": 0, "silver": 5, "gold": 10, "platinum": 15}

    @pytest.mark.parametrize(
        "tier",
        ["diamond", "", "Silver", "GOLD", "bronze ", None, 5, ("bronze",)],
    )
    def test_unknown_tier(self, tier):
        with pytest.raises(ValueError, match="unknown tier"):
            apply_tier_discount(1000, tier)

    @pytest.mark.parametrize("total_cents", [-1, -100, -10**9])
    def test_negative_total(self, total_cents):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            apply_tier_discount(total_cents, "bronze")

    def test_negative_total_checked_before_unknown_tier(self):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            apply_tier_discount(-1, "diamond")


# ---------------------------------------------------------------------------
# ordercalc.discounts.bulk_discount_percent
# ---------------------------------------------------------------------------

class TestBulkDiscountPercent:

    @pytest.mark.parametrize(
        ("qty", "expected"),
        [
            (0, 0),
            (1, 0),
            (5, 0),
            (9, 0),
            (10, 3),      # граница «от 10» включительно
            (11, 3),
            (25, 3),
            (49, 3),
            (50, 7),      # граница «от 50» включительно
            (51, 7),
            (75, 7),
            (99, 7),
            (100, 12),    # граница «от 100» включительно
            (101, 12),
            (1000, 12),
            (10**6, 12),
        ],
    )
    def test_values_and_thresholds(self, qty, expected):
        assert bulk_discount_percent(qty) == expected

    @pytest.mark.parametrize("qty", [-1, -10, -10**6])
    def test_negative_qty(self, qty):
        with pytest.raises(ValueError, match="qty must be >= 0"):
            bulk_discount_percent(qty)


# ---------------------------------------------------------------------------
# ordercalc.loyalty.points_for_order
# ---------------------------------------------------------------------------

class TestPointsForOrder:

    @pytest.mark.parametrize(
        ("total_cents", "history_cents", "expected"),
        [
            (0, 0, 0),
            (99, 0, 0),
            (100, 0, 1),
            (199, 0, 1),
            (200, 0, 2),
            (10099, 0, 100),
            (12345, 0, 123),
            (10**8, 0, 10**6),
            (10000, 1, 100),
            (10000, 99999, 100),    # порог x2 не достигнут
            (10000, 100000, 200),   # граница x2 включительно
            (10000, 100001, 200),
            (10000, 499999, 200),
            (10000, 500000, 300),   # граница x3 включительно (больший порог приоритетен)
            (10000, 500001, 300),
            (10000, 10**9, 300),
            (0, 500000, 0),
            (333, 500000, 9),       # 3 полные сотни * 3
            (100, 499999, 2),
        ],
    )
    def test_values_and_multiplier_thresholds(self, total_cents, history_cents, expected):
        assert points_for_order(total_cents, history_cents) == expected

    def test_history_defaults_to_zero(self):
        assert points_for_order(25000) == 250
        assert points_for_order(25000, 0) == 250

    @pytest.mark.parametrize("total_cents", [-1, -100])
    def test_negative_total(self, total_cents):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            points_for_order(total_cents, 0)

    @pytest.mark.parametrize("history_cents", [-1, -100])
    def test_negative_history(self, history_cents):
        with pytest.raises(ValueError, match="history_cents must be >= 0"):
            points_for_order(0, history_cents)

    def test_negative_total_checked_first(self):
        with pytest.raises(ValueError, match="total_cents must be >= 0"):
            points_for_order(-1, -1)


# ---------------------------------------------------------------------------
# ordercalc.loyalty.expire_points
# ---------------------------------------------------------------------------

class TestExpirePoints:

    def test_empty_entries(self):
        assert expire_points([], date(2024, 6, 1)) == 0

    @pytest.mark.parametrize(
        ("accrued_iso", "on_iso", "points", "expected"),
        [
            # день начисления включается
            ("2024-01-10", "2024-01-10", 100, 100),
            # день до начисления не считается
            ("2024-01-10", "2024-01-09", 100, 0),
            # последний день действия: accrual + 365
            ("2024-01-10", "2025-01-09", 100, 100),
            # accrual + 366 — балл истёк
            ("2024-01-10", "2025-01-10", 100, 0),
            # невисокосный год: 365 дней = та же дата через год
            ("2023-01-10", "2024-01-10", 50, 50),
            ("2023-01-10", "2024-01-11", 50, 0),
            # високосный 2024: 29.02.2024 + 365 дней = 28.02.2025
            ("2024-02-29", "2025-02-27", 10, 10),
            ("2024-02-29", "2025-02-28", 10, 10),
            ("2024-02-29", "2025-03-01", 10, 0),
            # начало високосного года: 01.01.2024 + 365 = 31.12.2024
            ("2024-01-01", "2024-12-31", 5, 5),
            ("2024-01-01", "2025-01-01", 5, 0),
            # интервал без 29 февраля внутри: 365 дней
            ("2024-03-01", "2025-03-01", 7, 7),
            ("2024-03-01", "2025-03-02", 7, 0),
            # будущее начисление не учитывается
            ("2030-01-01", "2024-01-01", 5, 0),
            # ноль баллов
            ("2024-01-01", "2024-06-01", 0, 0),
        ],
    )
    def test_single_entry_boundaries(self, accrued_iso, on_iso, points, expected):
        assert expire_points(
            [(accrued_iso, points)], date.fromisoformat(on_iso)
        ) == expected

    def test_sums_only_valid_entries(self):
        entries = [
            ("2024-01-01", 10),
            ("2024-06-01", 20),
            ("2023-05-05", 40),   # истёк к 31.12.2024 (2023-05-05 + 365 = 2024-05-04)
            ("2030-01-01", 50),   # ещё не начислен
        ]
        assert expire_points(entries, date(2024, 12, 31)) == 30

    def test_several_entries_same_day(self):
        entries = [("2024-01-01", 10), ("2024-01-02", 20)]
        assert expire_points(entries, date(2024, 1, 2)) == 30

    def test_accepts_list_of_lists(self):
        assert expire_points([["2024-01-01", 8]], date(2024, 5, 5)) == 8

    @pytest.mark.parametrize("bad_iso", ["not-a-date", "2024-13-45", "2024-02-30", ""])
    def test_invalid_date_string(self, bad_iso):
        with pytest.raises(ValueError):
            expire_points([(bad_iso, 5)], date(2024, 6, 1))


# ---------------------------------------------------------------------------
# ordercalc.split.split_payment
# ---------------------------------------------------------------------------

class TestSplitPayment:

    @pytest.mark.parametrize(
        ("amount_cents", "parts", "expected"),
        [
            (1, 1, [1]),
            (10, 1, [10]),
            (10, 2, [5, 5]),
            (10, 3, [4, 3, 3]),
            (11, 4, [3, 3, 3, 2]),
            (12, 4, [3, 3, 3, 3]),
            (10, 10, [1] * 10),
            (5, 5, [1, 1, 1, 1, 1]),
            (7, 7, [1] * 7),
            (100, 7, [15, 15, 14, 14, 14, 14, 14]),
            (101, 10, [11] + [10] * 9),
            (999, 2, [500, 499]),
        ],
    )
    def test_values(self, amount_cents, parts, expected):
        assert split_payment(amount_cents, parts) == expected

    @pytest.mark.parametrize(
        ("amount_cents", "parts"),
        [(10, 1), (12, 4), (100, 7), (7, 7), (12345, 17)],
    )
    def test_invariants(self, amount_cents, parts):
        result = split_payment(amount_cents, parts)
        assert isinstance(result, list)
        assert len(result) == parts
        assert sum(result) == amount_cents
        assert all(p >= 0 for p in result)
        # части отличаются не более чем на один цент
        assert max(result) - min(result) <= 1

    @pytest.mark.parametrize(
        ("amount_cents", "parts"),
        [(0, 1), (0, 5), (5, 6), (9, 10), (99, 100)],
    )
    def test_amount_less_than_parts(self, amount_cents, parts):
        with pytest.raises(
            ValueError, match="amount_cents is less than number of parts"
        ):
            split_payment(amount_cents, parts)

    @pytest.mark.parametrize("parts", [0, -1, -10])
    def test_invalid_parts(self, parts):
        with pytest.raises(ValueError, match="parts must be >= 1"):
            split_payment(100, parts)

    @pytest.mark.parametrize("amount_cents", [-1, -100])
    def test_negative_amount(self, amount_cents):
        with pytest.raises(ValueError, match="amount_cents must be >= 0"):
            split_payment(amount_cents, 2)


# ---------------------------------------------------------------------------
# ordercalc.split.split_weighted
# ---------------------------------------------------------------------------

class TestSplitWeighted:

    @pytest.mark.parametrize(
        ("amount_cents", "weights", "expected"),
        [
            (50, [1], [50]),
            (100, [1, 1], [50, 50]),
            (100, [0, 100], [0, 100]),
            (7, [0, 1], [0, 7]),
            (5, [1, 1, 3], [1, 1, 3]),
            (7, [2, 5], [2, 5]),
            (10, [3, 3, 4], [3, 3, 4]),
            (99, [1, 1, 1], [33, 33, 33]),
            (100, [1, 1, 1], [34, 33, 33]),    # равные дробные части — выигрывает первая
            (101, [1, 1, 1], [34, 34, 33]),
            (1, [1, 1, 1], [1, 0, 0]),
            (10, [1, 1, 1], [4, 3, 3]),
            (100, [1, 2], [33, 67]),
            (100, [1, 2, 3], [17, 33, 50]),
            (12345, [7, 3], [8642, 3703]),     # ничья .5/.5 — цент идёт более ранней части
            (777, [1, 0, 4], [155, 0, 622]),   # нулевой вес остаётся нулевым
            (0, [5, 5], [0, 0]),
            (0, [0, 3], [0, 0]),
            (1000, [1, 1, 1, 1, 1], [200, 200, 200, 200, 200]),
            (3, [1, 1, 1], [1, 1, 1]),
        ],
    )
    def test_values(self, amount_cents, weights, expected):
        assert split_weighted(amount_cents, weights) == expected

    @pytest.mark.parametrize(
        ("amount_cents", "weights"),
        [
            (100, [1, 1, 1]),
            (999, [2, 3, 5, 7]),
            (12345, [7, 3]),
            (777, [1, 0, 4]),
            (0, [3, 4]),
            (10**6, [13, 17, 19]),
        ],
    )
    def test_invariants(self, amount_cents, weights):
        result = split_weighted(amount_cents, weights)
        assert isinstance(result, list)
        assert len(result) == len(weights)
        assert sum(result) == amount_cents
        assert all(p >= 0 for p in result)

    def test_accepts_tuple_of_weights(self):
        assert split_weighted(100, (1, 1)) == [50, 50]

    @pytest.mark.parametrize("amount_cents", [-1, -100])
    def test_negative_amount(self, amount_cents):
        with pytest.raises(ValueError, match="amount_cents must be >= 0"):
            split_weighted(amount_cents, [1, 2])

    @pytest.mark.parametrize("weights", [[], ()])
    def test_empty_weights(self, weights):
        with pytest.raises(ValueError, match="weights must not be empty"):
            split_weighted(10, weights)

    @pytest.mark.parametrize("weights", [[0], [0, 0, 0]])
    def test_zero_sum_weights(self, weights):
        with pytest.raises(ValueError, match="weights sum must be > 0"):
            split_weighted(10, weights)

    @pytest.mark.parametrize("weights", [[-1], [1, -5], [0, -100]])
    def test_negative_weights(self, weights):
        with pytest.raises(ValueError, match="weights must be >= 0"):
            split_weighted(10, weights)
