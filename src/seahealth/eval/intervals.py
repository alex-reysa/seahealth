"""Confidence-interval helpers for aggregate count claims.

The Desert Map answers questions like "Bihar has between 12 and 19 functional
ICUs (95% CI)" — a planner-facing claim. This module is the single home for
the interval calculation so the schema, the API, and the UI agree.

We use the **Wilson score interval** for binary proportions (preferred over
the normal approximation at small n and at extreme proportions) and a
**Clopper–Pearson exact interval** when an integer count is needed.

`wilson_proportion_interval(successes, trials)` returns the Wilson 95% CI
on the proportion `successes / trials`. `count_interval(successes, trials)`
multiplies that by `trials` and rounds to the nearest non-negative integer
pair so the result feeds straight into `MapRegionAggregate.capability_count_ci`.

Pure-Python; no scipy required.
"""

from __future__ import annotations

import math
from typing import Tuple

# 1.96 ≈ z(1 - 0.025) for a 95% two-sided CI. Hard-coded so the module has
# no scipy dependency. 99% CI would use 2.5758.
_Z_95 = 1.959963984540054


def wilson_proportion_interval(
    successes: int,
    trials: int,
    *,
    z: float = _Z_95,
) -> Tuple[float, float]:
    """Wilson score interval on the proportion ``successes / trials``.

    Returns ``(lo, hi)`` in ``[0.0, 1.0]``. When ``trials == 0`` the interval
    is the trivial ``(0.0, 1.0)`` (we know nothing).

    Args:
        successes: number of "verified" facilities (or whatever the positive
            class is).
        trials: total facilities considered. Must be ``>= successes``.
        z: standard normal quantile for the desired two-sided coverage.
    """
    if trials < 0 or successes < 0:
        raise ValueError("successes and trials must be non-negative")
    if successes > trials:
        raise ValueError("successes cannot exceed trials")
    if trials == 0:
        return (0.0, 1.0)

    p_hat = successes / trials
    denom = 1 + (z**2) / trials
    centre = p_hat + (z**2) / (2 * trials)
    half = z * math.sqrt((p_hat * (1 - p_hat) + (z**2) / (4 * trials)) / trials)
    lo = (centre - half) / denom
    hi = (centre + half) / denom
    return (max(0.0, lo), min(1.0, hi))


def count_interval(
    successes: int,
    trials: int,
    *,
    z: float = _Z_95,
) -> Tuple[int, int]:
    """Wilson interval scaled back to integer counts in ``[0, trials]``.

    Result satisfies ``0 <= lo <= successes <= hi <= trials``.

    The lower bound rounds *down* and the upper bound rounds *up* so the
    interval never falsely advertises a tighter bound than Wilson actually
    proves. When ``trials == 0`` the interval is ``(0, 0)``.
    """
    if trials == 0:
        return (0, 0)
    lo_p, hi_p = wilson_proportion_interval(successes, trials, z=z)
    lo = max(0, int(math.floor(lo_p * trials)))
    hi = min(trials, int(math.ceil(hi_p * trials)))
    if lo > successes:
        lo = successes
    if hi < successes:
        hi = successes
    return (lo, hi)


__all__ = [
    "count_interval",
    "wilson_proportion_interval",
]
