from datetime import date, timedelta

import pytest

import ordercalc
from ordercalc import discounts, loyalty, split
from ordercalc.discounts import apply_tier_discount, bulk_discount_percent
from ordercalc.loyalty import expire_points, points_for_order
from ordercalc.split import split_payment, split_weighted

ALL_TIERS = ("bronze", "silver", "gold", "platinum")

SPLIT_PAYMENT_VALID_CASES = [
    (100, 4),
    (101, 4),
    (103, 4),
    (10, 3),
    (100, 3),
    (1000, 3),
    (5, 1),
    (7, 7),
    (7, 6),
    (11, 10),
    (19, 10),
    (6, 4),
    (9, 3),
    (1, 1),
]

SPLIT_PAYMENT_POSITIVE_CASES = [
    (amount, parts) for amount, parts in SPLIT_PAYMENT_VALID_CASES if amount >= parts
]

SPLIT_WEIGHTED_VALID_CASES = [
    (100, [50, 50]),
    (100, [1, 1, 1]),
    (100, [1, 1, 1, 1]),
    (100, [1, 2]),
    (100, [2, 3]),
    (99, [2, 3]),
    (101, [2, 3]),
    (50, [1, 1, 1]),
    (101, [1, 1, 1]),
    (103, [1, 1, 1]),
    (10, [1, 1, 1]),
    (3, [1, 1, 1]),
    (2, [1, 1, 1]),
    (1, [1, 1]),
    (1, [1, 1, 1]),
    (100, [1, 1, 2]),
    (100, [3, 3, 3, 1]),
    (101, [3, 3, 3, 1]),
    (1000, [1, 0, 1]),
    (100, [0, 0, 1]),
    (5, [3, 2]),
    (7, [1, 2, 4]),
    (0, [1, 2, 3]),
    (100, [7]),
    (0, [7]),
    (1, [1, 3]),
    (100, [0, 1]),
]

SPLIT_WEIGHTED_ZERO_WEIGHT_CASES = [
    (1000, [1, 0, 1]),
    (100, [0, 0, 1]),
    (100, [0, 1]),
]


@pytest.mark.parametrize(
    ("total_cents", "tier", "expected"),
    [
        (1000, "bronze", 1000),
        (1000, "silver", 950),
        (1000, "gold", 900),
        (1000, "platinum", 850),
        (100, "silver", 95),
        (20, "silver", 19),
        (12345, "bronze", 12345),
        (12345, "silver", 11728),
        (999, "gold", 899),
        (999, "platinum", 849),
        (12345, "gold", 11111),
    ],
)
def test_apply_tier_discount_typical(total_cents, tier, expected):
    assert apply_tier_discount(total_cents, tier) == expected


@pytest.mark.parametrize("tier", ALL_TIERS)
def test_apply_tier_discount_zero_total(tier):
    assert apply_tier_discount(0, tier) == 0


@pytest.mark.parametrize(
    ("total_cents", "tier", "expected"),
    [
        (10, "platinum", 9),
        (30, "silver", 29),
        (25, "gold", 23),
        (110, "silver", 105),
        (50, "platinum", 43),
        (12345, "gold", 11111),
        (5, "gold", 5),
        (10, "silver", 10),
        (30, "platinum", 26),
        (110, "platinum", 94),
    ],
)
def test_apply_tier_discount_half_up_rounding(total_cents, tier, expected):
    assert apply_tier_discount(total_cents, tier) == expected


@pytest.mark.parametrize(
    ("total_cents", "tier", "expected"),
    [
        (1, "bronze", 1),
        (1, "silver", 1),
        (1, "gold", 1),
        (1, "platinum", 1),
        (2, "platinum", 2),
        (9, "platinum", 8),
    ],
)
def test_apply_tier_discount_fraction_near_half(total_cents, tier, expected):
    assert apply_tier_discount(total_cents, tier) == expected


@pytest.mark.parametrize(
    ("total_cents", "tier", "message"),
    [
        (-1, "gold", r"total_cents must be >= 0"),
        (-100, 0, r"total_cents must be >= 0"),
        (0, -100, r"unknown tier: -100"),
        (100, "diamond", r"unknown tier: 'diamond'"),
        (100, "Gold", r"unknown tier: 'Gold'"),
        (100, "GOLD", r"unknown tier: 'GOLD'"),
        (100, "", r"unknown tier: ''"),
        (100, "gold ", r"unknown tier: 'gold '"),
        (100, None, r"unknown tier: None"),
    ],
)
def test_apply_tier_discount_invalid_input(total_cents, tier, message):
    with pytest.raises(ValueError, match=message):
        apply_tier_discount(total_cents, tier)


def test_apply_tier_discount_negative_total_checked_before_tier():
    with pytest.raises(ValueError, match=r"total_cents must be >= 0"):
        apply_tier_discount(-1, "diamond")


def test_apply_tier_discount_returns_int():
    assert isinstance(apply_tier_discount(1000, "silver"), int)
    assert isinstance(apply_tier_discount(12345, "gold"), int)


@pytest.mark.parametrize("total_cents", [0, 1, 7, 99, 100, 999, 12345, 999999])
@pytest.mark.parametrize("tier", ALL_TIERS)
def test_apply_tier_discount_result_within_bounds(total_cents, tier):
    result = apply_tier_discount(total_cents, tier)
    assert 0 <= result <= total_cents


@pytest.mark.parametrize("total_cents", [0, 1, 10, 999, 12345])
def test_apply_tier_discount_bronze_returns_input(total_cents):
    assert apply_tier_discount(total_cents, "bronze") == total_cents


@pytest.mark.parametrize("total_cents", [0, 10, 1000, 12345])
def test_apply_tier_discount_monotonic_by_tier(total_cents):
    results = [apply_tier_discount(total_cents, tier) for tier in ALL_TIERS]
    assert results == sorted(results, reverse=True)


@pytest.mark.parametrize(
    ("qty", "expected"),
    [
        (0, 0),
        (1, 0),
        (5, 0),
        (10, 3),
        (25, 3),
        (50, 7),
        (75, 7),
        (100, 12),
        (250, 12),
        (1000000, 12),
    ],
)
def test_bulk_discount_percent_typical(qty, expected):
    assert bulk_discount_percent(qty) == expected


@pytest.mark.parametrize(
    ("qty", "expected"),
    [
        (9, 0),
        (10, 3),
        (49, 3),
        (50, 7),
        (99, 7),
        (100, 12),
        (101, 12),
    ],
)
def test_bulk_discount_percent_threshold_inclusive(qty, expected):
    assert bulk_discount_percent(qty) == expected


@pytest.mark.parametrize("qty", [-1, -100])
def test_bulk_discount_percent_negative_qty(qty):
    with pytest.raises(ValueError, match=r"qty must be >= 0"):
        bulk_discount_percent(qty)


def test_bulk_discount_percent_returns_int():
    assert isinstance(bulk_discount_percent(10), int)
    assert isinstance(bulk_discount_percent(0), int)


@pytest.mark.parametrize("qty", [0, 1, 9, 10, 49, 50, 99, 100, 101, 1000, 1000000])
def test_bulk_discount_percent_allowed_values(qty):
    assert bulk_discount_percent(qty) in {0, 3, 7, 12}


def test_bulk_discount_percent_monotonic():
    values = [bulk_discount_percent(qty) for qty in range(0, 130)]
    assert values == sorted(values)


@pytest.mark.parametrize(
    ("amount_cents", "parts", "expected"),
    [
        (100, 4, [25, 25, 25, 25]),
        (101, 4, [26, 25, 25, 25]),
        (103, 4, [26, 26, 26, 25]),
        (10, 3, [4, 3, 3]),
        (100, 3, [34, 33, 33]),
        (1000, 3, [334, 333, 333]),
        (5, 1, [5]),
        (7, 6, [2, 1, 1, 1, 1, 1]),
        (11, 10, [2, 1, 1, 1, 1, 1, 1, 1, 1, 1]),
        (19, 10, [2, 2, 2, 2, 2, 2, 2, 2, 2, 1]),
        (6, 4, [2, 2, 1, 1]),
    ],
)
def test_split_payment_typical(amount_cents, parts, expected):
    assert split_payment(amount_cents, parts) == expected


@pytest.mark.parametrize(
    ("amount_cents", "parts", "expected"),
    [
        (1, 1, [1]),
        (7, 7, [1, 1, 1, 1, 1, 1, 1]),
        (9, 3, [3, 3, 3]),
    ],
)
def test_split_payment_boundary(amount_cents, parts, expected):
    assert split_payment(amount_cents, parts) == expected


@pytest.mark.parametrize(
    ("amount_cents", "parts"),
    [(0, 1), (0, 2), (2, 3), (5, 6), (3, 5)],
)
def test_split_payment_amount_less_than_parts(amount_cents, parts):
    with pytest.raises(ValueError, match=r"amount_cents is less than number of parts"):
        split_payment(amount_cents, parts)


@pytest.mark.parametrize(
    ("amount_cents", "parts", "message"),
    [
        (-1, 2, r"amount_cents must be >= 0"),
        (-100, 1, r"amount_cents must be >= 0"),
        (100, 0, r"parts must be >= 1"),
        (100, -3, r"parts must be >= 1"),
        (0, 0, r"parts must be >= 1"),
        (-5, 0, r"amount_cents must be >= 0"),
    ],
)
def test_split_payment_invalid_input(amount_cents, parts, message):
    with pytest.raises(ValueError, match=message):
        split_payment(amount_cents, parts)


@pytest.mark.parametrize(("amount_cents", "parts"), SPLIT_PAYMENT_VALID_CASES)
def test_split_payment_sum_matches_amount(amount_cents, parts):
    assert sum(split_payment(amount_cents, parts)) == amount_cents


@pytest.mark.parametrize(("amount_cents", "parts"), SPLIT_PAYMENT_VALID_CASES)
def test_split_payment_length_equals_parts(amount_cents, parts):
    assert len(split_payment(amount_cents, parts)) == parts


@pytest.mark.parametrize(("amount_cents", "parts"), SPLIT_PAYMENT_VALID_CASES)
def test_split_payment_parts_differ_by_at_most_one(amount_cents, parts):
    result = split_payment(amount_cents, parts)
    assert max(result) - min(result) <= 1


@pytest.mark.parametrize(("amount_cents", "parts"), SPLIT_PAYMENT_POSITIVE_CASES)
def test_split_payment_parts_positive(amount_cents, parts):
    assert all(part > 0 for part in split_payment(amount_cents, parts))


@pytest.mark.parametrize(("amount_cents", "parts"), SPLIT_PAYMENT_VALID_CASES)
def test_split_payment_non_increasing(amount_cents, parts):
    result = split_payment(amount_cents, parts)
    assert result == sorted(result, reverse=True)


def test_split_payment_returns_int_list():
    result = split_payment(101, 4)
    assert isinstance(result, list)
    assert all(isinstance(part, int) for part in result)


@pytest.mark.parametrize(
    ("amount_cents", "weights", "expected"),
    [
        (100, [50, 50], [50, 50]),
        (100, [1, 1, 1], [34, 33, 33]),
        (100, [1, 1, 1, 1], [25, 25, 25, 25]),
        (100, [1, 2], [33, 67]),
        (100, [2, 3], [40, 60]),
        (99, [2, 3], [40, 59]),
        (101, [2, 3], [40, 61]),
        (50, [1, 1, 1], [17, 17, 16]),
        (101, [1, 1, 1], [34, 34, 33]),
        (103, [1, 1, 1], [35, 34, 34]),
        (10, [1, 1, 1], [4, 3, 3]),
        (3, [1, 1, 1], [1, 1, 1]),
        (2, [1, 1, 1], [1, 1, 0]),
        (1, [1, 1], [1, 0]),
        (1, [1, 1, 1], [1, 0, 0]),
        (100, [1, 1, 2], [25, 25, 50]),
        (100, [3, 3, 3, 1], [30, 30, 30, 10]),
        (101, [3, 3, 3, 1], [31, 30, 30, 10]),
        (1000, [1, 0, 1], [500, 0, 500]),
        (100, [0, 0, 1], [0, 0, 100]),
        (5, [3, 2], [3, 2]),
        (7, [1, 2, 4], [1, 2, 4]),
    ],
)
def test_split_weighted_typical(amount_cents, weights, expected):
    assert split_weighted(amount_cents, weights) == expected


@pytest.mark.parametrize(
    ("amount_cents", "weights", "expected"),
    [
        (0, [1, 2, 3], [0, 0, 0]),
        (100, [7], [100]),
        (0, [7], [0]),
        (1, [1, 1], [1, 0]),
        (1, [1, 3], [0, 1]),
        (101, [3, 3, 3, 1], [31, 30, 30, 10]),
        (100, [0, 1], [0, 100]),
    ],
)
def test_split_weighted_boundary(amount_cents, weights, expected):
    assert split_weighted(amount_cents, weights) == expected


@pytest.mark.parametrize(
    ("amount_cents", "weights", "message"),
    [
        (-1, [1, 2], r"amount_cents must be >= 0"),
        (100, [], r"weights must not be empty"),
        (0, [], r"weights must not be empty"),
        (100, [1, -1], r"weights must be >= 0"),
        (100, [-5, 10], r"weights must be >= 0"),
        (100, [0, 0], r"weights sum must be > 0"),
        (0, [0, 0, 0], r"weights sum must be > 0"),
        (-1, [], r"amount_cents must be >= 0"),
        (-1, [-2], r"amount_cents must be >= 0"),
    ],
)
def test_split_weighted_invalid_input(amount_cents, weights, message):
    with pytest.raises(ValueError, match=message):
        split_weighted(amount_cents, weights)


@pytest.mark.parametrize(("amount_cents", "weights"), SPLIT_WEIGHTED_VALID_CASES)
def test_split_weighted_sum_matches_amount(amount_cents, weights):
    assert sum(split_weighted(amount_cents, weights)) == amount_cents


@pytest.mark.parametrize(("amount_cents", "weights"), SPLIT_WEIGHTED_VALID_CASES)
def test_split_weighted_length_matches_weights(amount_cents, weights):
    assert len(split_weighted(amount_cents, weights)) == len(weights)


@pytest.mark.parametrize(("amount_cents", "weights"), SPLIT_WEIGHTED_ZERO_WEIGHT_CASES)
def test_split_weighted_zero_weight_gets_zero(amount_cents, weights):
    result = split_weighted(amount_cents, weights)
    assert all(part == 0 for part, weight in zip(result, weights) if weight == 0)


@pytest.mark.parametrize(("amount_cents", "weights"), SPLIT_WEIGHTED_VALID_CASES)
def test_split_weighted_part_is_floor_or_floor_plus_one(amount_cents, weights):
    total_weight = sum(weights)
    result = split_weighted(amount_cents, weights)
    for part, weight in zip(result, weights):
        base = amount_cents * weight // total_weight
        assert part in (base, base + 1)


def test_split_weighted_equal_weights_match_split_payment():
    assert split_weighted(101, [1, 1, 1]) == split_payment(101, 3) == [34, 34, 33]


def test_split_weighted_returns_int_list():
    result = split_weighted(101, [2, 3])
    assert isinstance(result, list)
    assert all(isinstance(part, int) for part in result)


@pytest.mark.parametrize(
    ("total_cents", "history_cents", "expected"),
    [
        (0, 0, 0),
        (99, 0, 0),
        (100, 0, 1),
        (199, 0, 1),
        (250, 0, 2),
        (9999, 0, 99),
        (12345, 0, 123),
        (1000, 0, 10),
        (1000, 50000, 10),
        (1000, 100000, 20),
        (1000, 250000, 20),
        (1000, 499999, 20),
        (1000, 500000, 30),
        (1000, 1000000, 30),
        (1500, 250000, 30),
        (1500, 600000, 45),
        (0, 500000, 0),
        (99, 500000, 0),
        (12345, 100000, 246),
        (12345, 500000, 369),
    ],
)
def test_points_for_order_typical(total_cents, history_cents, expected):
    assert points_for_order(total_cents, history_cents) == expected


def test_points_for_order_default_history():
    assert points_for_order(0) == 0
    assert points_for_order(1000) == 10


@pytest.mark.parametrize(
    ("total_cents", "history_cents", "expected"),
    [
        (1000, 99999, 10),
        (1000, 100000, 20),
        (1000, 499999, 20),
        (1000, 500000, 30),
    ],
)
def test_points_for_order_threshold_inclusive(total_cents, history_cents, expected):
    assert points_for_order(total_cents, history_cents) == expected


@pytest.mark.parametrize(
    ("total_cents", "expected"),
    [
        (99, 0),
        (100, 1),
        (101, 1),
        (199, 1),
        (200, 2),
    ],
)
def test_points_for_order_floor_of_hundreds(total_cents, expected):
    assert points_for_order(total_cents, 0) == expected


def test_points_for_order_multiplier_takes_largest_threshold():
    assert points_for_order(1000, 500000) == 30
    assert points_for_order(1500, 600000) == 45


@pytest.mark.parametrize(
    ("total_cents", "history_cents", "message"),
    [
        (-1, 0, r"total_cents must be >= 0"),
        (-100, 1000, r"total_cents must be >= 0"),
        (100, -1, r"history_cents must be >= 0"),
        (100, -100000, r"history_cents must be >= 0"),
        (-1, -1, r"total_cents must be >= 0"),
        (0, -1, r"history_cents must be >= 0"),
    ],
)
def test_points_for_order_invalid_input(total_cents, history_cents, message):
    with pytest.raises(ValueError, match=message):
        points_for_order(total_cents, history_cents)


def test_points_for_order_returns_int():
    assert isinstance(points_for_order(12345, 500000), int)
    assert isinstance(points_for_order(1000), int)


@pytest.mark.parametrize(
    ("total_cents", "history_cents"),
    [
        (100, 0),
        (100, 100000),
        (1000, 0),
        (1000, 100000),
        (1000, 500000),
        (12345, 500000),
    ],
)
def test_points_for_order_multiple_of_base(total_cents, history_cents):
    base = total_cents // 100
    assert points_for_order(total_cents, history_cents) % base == 0


@pytest.mark.parametrize("total_cents", [100, 1000, 12345])
def test_points_for_order_triple_at_max_history(total_cents):
    assert points_for_order(total_cents, 500000) == 3 * points_for_order(total_cents, 0)


@pytest.mark.parametrize("history_cents", [0, 99999, 100000, 499999, 500000, 1000000])
def test_points_for_order_small_total_always_zero(history_cents):
    assert points_for_order(99, history_cents) == 0


def test_expire_points_accrual_day_valid():
    assert expire_points([("2024-01-01", 10)], date(2024, 1, 1)) == 10


def test_expire_points_last_day_normal_year():
    assert expire_points([("2023-01-01", 10)], date(2024, 1, 1)) == 10


def test_expire_points_first_day_after_expiry():
    assert expire_points([("2023-01-01", 10)], date(2024, 1, 2)) == 0


def test_expire_points_mixed_expired_and_valid():
    entries = [("2024-01-01", 10), ("2024-06-15", 20), ("2020-01-01", 100)]
    assert expire_points(entries, date(2024, 7, 1)) == 30


def test_expire_points_all_expired():
    entries = [("2020-01-01", 50), ("2021-05-05", 60)]
    assert expire_points(entries, date(2024, 7, 1)) == 0


def test_expire_points_empty_list():
    assert expire_points([], date(2024, 7, 1)) == 0


def test_expire_points_future_accrual():
    assert expire_points([("2024-06-01", 10)], date(2024, 5, 31)) == 0


def test_expire_points_zero_points():
    assert expire_points([("2024-01-01", 0)], date(2024, 1, 1)) == 0


@pytest.mark.parametrize(
    ("entries", "on_date", "expected"),
    [
        ([("2024-01-01", 10)], date(2024, 1, 1), 10),
        ([("2024-01-01", 10)], date(2024, 12, 31), 10),
        ([("2024-01-01", 10)], date(2025, 1, 1), 0),
        ([("2023-01-01", 10)], date(2024, 1, 1), 10),
        ([("2023-01-01", 10)], date(2024, 1, 2), 0),
        ([("2023-03-01", 5)], date(2024, 2, 28), 5),
        ([("2023-03-01", 5)], date(2024, 2, 29), 5),
        ([("2023-03-01", 5)], date(2024, 3, 1), 0),
        ([("2024-02-29", 5)], date(2025, 2, 28), 5),
        ([("2024-02-29", 5)], date(2025, 3, 1), 0),
        ([("2023-12-31", 10)], date(2024, 12, 30), 10),
        ([("2023-12-31", 10)], date(2024, 12, 31), 0),
        ([("2024-01-01", 10)], date(2023, 12, 31), 0),
    ],
)
def test_expire_points_window_365_days_boundaries(entries, on_date, expected):
    assert expire_points(entries, on_date) == expected


@pytest.mark.parametrize(
    "iso",
    [
        "2024-13-01",
        "2024-02-30",
        "01-01-2024",
        "2024/01/01",
        "2024-1-1",
        "not-a-date",
    ],
)
def test_expire_points_invalid_isoformat(iso):
    with pytest.raises(ValueError):
        expire_points([(iso, 10)], date(2024, 7, 1))


def test_expire_points_window_includes_both_ends():
    entries = [("2024-01-01", 10)]
    accrual = date(2024, 1, 1)
    assert expire_points(entries, accrual) == 10
    assert expire_points(entries, accrual + timedelta(days=365)) == 10
    assert expire_points(entries, accrual + timedelta(days=366)) == 0


def test_expire_points_order_independent():
    entries = [("2024-01-01", 10), ("2024-06-15", 20), ("2023-05-05", 5)]
    on_date = date(2024, 7, 1)
    assert expire_points(entries, on_date) == expire_points(list(reversed(entries)), on_date)


def test_ordercalc_package_import():
    assert ordercalc.__name__ == "ordercalc"


def test_ordercalc_all():
    assert ordercalc.__all__ == ["discounts", "split", "loyalty"]


def test_ordercalc_submodules():
    assert ordercalc.discounts is discounts
    assert ordercalc.split is split
    assert ordercalc.loyalty is loyalty


def test_ordercalc_public_functions_importable():
    assert callable(apply_tier_discount)
    assert callable(bulk_discount_percent)
    assert callable(split_payment)
    assert callable(split_weighted)
    assert callable(points_for_order)
    assert callable(expire_points)
