#!/usr/bin/env python3
"""Verify the article's constructed arithmetic; no model or external input.

Python standard library only. All outcomes are deliberately constructed.
The estimator is implemented directly using integer combinations and exact
fractions; this small-number check is not a production evaluation harness.
"""
from fractions import Fraction
from itertools import combinations
from math import comb
import json


OUTCOMES = {
    "A": (1, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "B": (0, 1, 1, 0, 0, 0, 0, 0, 0, 0),
    "C": (1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    "D": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
}


def pass_estimate(n: int, c: int, k: int) -> Fraction:
    if not 0 <= c <= n or not 1 <= k <= n:
        raise ValueError("require 0 <= c <= n and 1 <= k <= n")
    failures_only = comb(n - c, k) if n - c >= k else 0
    return 1 - Fraction(failures_only, comb(n, k))


def mean(values):
    values = tuple(values)
    return sum(values, Fraction()) / len(values)


def pct(value):
    return float(100 * value)


def verify():
    rows = tuple(OUTCOMES.values())
    first = mean(row[0] for row in rows)
    repeated_mean = mean(Fraction(sum(row), len(row)) for row in rows)
    any_ten = mean(int(any(row)) for row in rows)
    all_ten = mean(int(all(row)) for row in rows)
    estimates = {
        k: mean(pass_estimate(len(row), sum(row), k) for row in rows)
        for k in range(1, 11)
    }
    prefix_rates = {
        k: mean(int(any(row[:k])) for row in rows)
        for k in range(1, 11)
    }
    assert first == Fraction(1, 2)
    assert repeated_mean == Fraction(13, 40)
    assert any_ten == Fraction(3, 4)
    assert all_ten == Fraction(1, 4)
    assert estimates[1] == repeated_mean
    assert estimates[10] == any_ten
    assert all(prefix_rates[k] <= prefix_rates[k + 1] for k in range(1, 10))

    # Check all valid n,c,k combinations up to n=30 with exact arithmetic.
    monotone_checks = 0
    for n in range(1, 31):
        for c in range(n + 1):
            previous = Fraction()
            for k in range(1, n + 1):
                current = pass_estimate(n, c, k)
                assert 0 <= previous <= current <= 1
                previous = current
                monotone_checks += 1

    # Independently enumerate finite subsets for small pools.
    subset_checks = 0
    for n in range(1, 9):
        for c in range(n + 1):
            row = (1,) * c + (0,) * (n - c)
            for k in range(1, n + 1):
                subsets = tuple(combinations(row, k))
                observed = Fraction(sum(any(s) for s in subsets), len(subsets))
                assert observed == pass_estimate(n, c, k)
                subset_checks += 1

    # The article's hypothetical strategies use true per-question probabilities.
    strategy_a_single = Fraction(4, 5)
    strategy_b_any_ten = 1 - Fraction(9, 10) ** 10
    assert strategy_b_any_ten < strategy_a_single

    # A plug-in estimate does not equal the finite-pool estimator.
    assert pass_estimate(10, 1, 10) == 1
    assert 1 - (1 - Fraction(1, 10)) ** 10 != pass_estimate(10, 1, 10)

    # Averaging per-question probabilities cannot generally be moved inside
    # the nonlinear expression: half always fail, half always succeed.
    correct_average_any_ten = mean(1 - (1 - p) ** 10 for p in (Fraction(0), Fraction(1)))
    incorrect_global_plugin = 1 - (1 - Fraction(1, 2)) ** 10
    assert correct_average_any_ten == Fraction(1, 2)
    assert incorrect_global_plugin != correct_average_any_ten

    # Confirm unsupported sample counts are rejected rather than extrapolated.
    for bad in ((0, 0, 1), (9, 1, 10), (10, 11, 1), (10, 1, 0)):
        try:
            pass_estimate(*bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid arguments: {bad}")

    return {
        "data_kind": "constructed_binary_outcomes_not_model_measurements",
        "outcomes": OUTCOMES,
        "percentages": {
            "first_candidate_accuracy": pct(first),
            "mean_correctness_over_repeats": pct(repeated_mean),
            "any_success_among_ten": pct(any_ten),
            "all_ten_correct": pct(all_ten),
        },
        "estimated_pass_at_k_percent": {str(k): pct(v) for k, v in estimates.items()},
        "nested_prefix_any_success_percent": {str(k): pct(v) for k, v in prefix_rates.items()},
        "hypothetical_strategy_a_single_percent": pct(strategy_a_single),
        "hypothetical_strategy_b_any_ten_percent": pct(strategy_b_any_ten),
        "monotonicity_cases_checked": monotone_checks,
        "finite_subset_cases_checked": subset_checks,
        "status": "all_assertions_passed",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
