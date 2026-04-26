"""Tests for ``seahealth.eval.intervals`` — Wilson + count CIs."""
from __future__ import annotations

import pytest

from seahealth.eval.intervals import count_interval, wilson_proportion_interval


def test_wilson_zero_trials_is_uninformative() -> None:
    assert wilson_proportion_interval(0, 0) == (0.0, 1.0)


def test_wilson_extreme_proportions() -> None:
    lo, hi = wilson_proportion_interval(0, 10)
    assert lo == pytest.approx(0.0, abs=1e-6)
    assert hi > 0.0
    lo, hi = wilson_proportion_interval(10, 10)
    assert hi == pytest.approx(1.0, abs=1e-6)
    assert lo < 1.0


def test_wilson_known_value() -> None:
    """Spot-check against a published Wilson value for p=0.5, n=10:
    approximately (0.2366, 0.7634).
    """
    lo, hi = wilson_proportion_interval(5, 10)
    assert lo == pytest.approx(0.2366, abs=5e-3)
    assert hi == pytest.approx(0.7634, abs=5e-3)


def test_wilson_validates_inputs() -> None:
    with pytest.raises(ValueError):
        wilson_proportion_interval(-1, 10)
    with pytest.raises(ValueError):
        wilson_proportion_interval(11, 10)


def test_count_interval_brackets_observed() -> None:
    lo, hi = count_interval(15, 100)
    assert 0 <= lo <= 15 <= hi <= 100
    # Wilson interval is non-trivial at n=100.
    assert hi - lo >= 5


def test_count_interval_zero_trials() -> None:
    assert count_interval(0, 0) == (0, 0)


def test_count_interval_full_trials() -> None:
    lo, hi = count_interval(50, 50)
    assert hi == 50
    # Lower bound is meaningfully below 50 at this sample size.
    assert lo < 50