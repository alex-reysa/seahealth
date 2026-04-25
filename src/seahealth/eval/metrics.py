"""Pure metric computations for the Naomi gold-eval harness.

No I/O lives here. `run_eval.py` is responsible for reading CSVs / parquet
and turning them into the simple ``list[tuple[...]]`` structures these
functions consume.

Conventions for edge cases (documented because callers will hit them):

- If both ``expected`` and ``predicted`` are empty, precision/recall/F1 are
  defined as 1.0 (vacuous truth — no claims, no errors).
- If ``predicted`` is empty but ``expected`` is not, precision is 1.0 (no
  false positives are possible) and recall is 0.0.
- If ``expected`` is empty but ``predicted`` is not, precision is 0.0
  (every prediction is a false positive) and recall is 1.0.

These conventions match scikit-learn's ``zero_division=1`` behaviour for
the precision-undefined case but make the recall-undefined case explicit.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from seahealth.schemas import CapabilityType, ContradictionType


def _safe_div(numerator: float, denominator: float, default: float) -> float:
    return numerator / denominator if denominator else default


@dataclass(frozen=True)
class BinaryMetrics:
    """Confusion-matrix counts plus derived precision/recall/F1.

    All four counts are non-negative. The derived ratios use the conventions
    documented at the top of this module.
    """

    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        if self.tp == 0 and self.fp == 0:
            # No predicted positives. Convention: 1.0 (no false positives possible).
            return 1.0
        return _safe_div(self.tp, self.tp + self.fp, 0.0)

    @property
    def recall(self) -> float:
        if self.tp == 0 and self.fn == 0:
            # No actual positives. Convention: 1.0.
            return 1.0
        return _safe_div(self.tp, self.tp + self.fn, 0.0)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if p == 0 and r == 0:
            return 0.0
        return _safe_div(2 * p * r, p + r, 0.0)

    @property
    def support(self) -> int:
        """Number of actual positives (TP + FN)."""
        return self.tp + self.fn

    def to_dict(self) -> dict:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "support": self.support,
        }


def _unique(seq: Iterable[tuple]) -> set[tuple]:
    """Deduplicate a sequence of tuples while preserving hashability."""
    return set(seq)


def compute_capability_metrics(
    expected: list[tuple[str, str]],
    predicted: list[tuple[str, CapabilityType]],
) -> BinaryMetrics:
    """Per-(facility, capability) binary classification.

    A "positive" is the presence of a (facility_id, CapabilityType) pair.

    - ``expected`` rows whose Naomi capability has no clean enum mapping
      (returned ``None`` from :func:`naomi_mapping.map_capability`) are
      dropped here, because they cannot be matched against the extractor's
      predictions. The eval report counts them separately under
      "unmappable rows" so they don't disappear silently.
    - Duplicate (facility, capability) pairs in either side are deduplicated.
    """
    from seahealth.eval.naomi_mapping import map_capability

    expected_pairs: set[tuple[str, CapabilityType]] = set()
    for facility_id, naomi_cap in expected:
        mapped = map_capability(naomi_cap)
        if mapped is None:
            continue
        expected_pairs.add((facility_id, mapped))

    predicted_pairs: set[tuple[str, CapabilityType]] = _unique(predicted)

    tp = len(expected_pairs & predicted_pairs)
    fp = len(predicted_pairs - expected_pairs)
    fn = len(expected_pairs - predicted_pairs)
    return BinaryMetrics(tp=tp, fp=fp, fn=fn, tn=0)


def compute_contradiction_metrics(
    expected: list[tuple[str, str, str]],
    predicted: list[tuple[str, CapabilityType, ContradictionType]],
) -> BinaryMetrics:
    """Per-(facility, capability) contradiction-presence classification.

    A "positive" is: Naomi marked this (facility, capability) row with a
    non-``none`` contradiction OR the validator emitted at least one
    Contradiction for that (facility, capability).

    We do NOT require the contradiction _type_ to match — only its presence.
    Type-level agreement is reported separately in the markdown report; it
    is too sparse to compute reliable precision/recall on the 30-50-row
    scale Naomi delivers.
    """
    from seahealth.eval.naomi_mapping import is_contradiction_label, map_capability

    # Build the universe of facility/capability pairs Naomi labeled.
    expected_positive: set[tuple[str, CapabilityType]] = set()
    expected_universe: set[tuple[str, CapabilityType]] = set()
    for facility_id, naomi_cap, naomi_contra in expected:
        mapped_cap = map_capability(naomi_cap)
        if mapped_cap is None:
            continue
        key = (facility_id, mapped_cap)
        expected_universe.add(key)
        if is_contradiction_label(naomi_contra):
            expected_positive.add(key)

    # Predicted positives: any (facility, cap) pair the validator flagged.
    predicted_positive: set[tuple[str, CapabilityType]] = {
        (facility_id, cap) for facility_id, cap, _ctype in predicted
    }
    # Restrict predictions to the labeled universe — predictions on facilities
    # Naomi didn't review can't be scored.
    predicted_positive &= expected_universe

    tp = len(expected_positive & predicted_positive)
    fp = len(predicted_positive - expected_positive)
    fn = len(expected_positive - predicted_positive)
    tn = len(expected_universe - expected_positive - predicted_positive)
    return BinaryMetrics(tp=tp, fp=fp, fn=fn, tn=tn)


__all__ = [
    "BinaryMetrics",
    "compute_capability_metrics",
    "compute_contradiction_metrics",
]
