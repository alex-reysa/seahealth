"""Tests for `seahealth.eval.metrics`.

The metric conventions for empty inputs are spelled out in the module
docstring. These tests pin them so a future refactor cannot silently
flip them.
"""
from __future__ import annotations

import pytest

from seahealth.eval.metrics import (
    BinaryMetrics,
    compute_capability_metrics,
    compute_contradiction_metrics,
)
from seahealth.schemas import CapabilityType, ContradictionType


def test_binary_metrics_basic_formulas():
    m = BinaryMetrics(tp=8, fp=2, fn=2, tn=0)
    assert m.precision == pytest.approx(0.8)
    assert m.recall == pytest.approx(0.8)
    assert m.f1 == pytest.approx(0.8)
    assert m.support == 10


def test_binary_metrics_zero_division_conventions():
    # No predicted positives, no actual positives -> vacuous 1.0.
    m = BinaryMetrics(tp=0, fp=0, fn=0, tn=5)
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0
    # Predicted positives but no actuals -> precision 0, recall vacuously 1.
    m = BinaryMetrics(tp=0, fp=3, fn=0, tn=0)
    assert m.precision == 0.0
    assert m.recall == 1.0
    assert m.f1 == 0.0
    # Actuals but no predictions -> precision vacuously 1, recall 0.
    m = BinaryMetrics(tp=0, fp=0, fn=4, tn=0)
    assert m.precision == 1.0
    assert m.recall == 0.0
    assert m.f1 == 0.0


def test_binary_metrics_to_dict_round_trip():
    m = BinaryMetrics(tp=3, fp=3, fn=1, tn=0)
    d = m.to_dict()
    assert d["tp"] == 3 and d["fp"] == 3 and d["fn"] == 1 and d["tn"] == 0
    assert d["support"] == 4
    assert d["precision"] == pytest.approx(0.5, abs=1e-4)
    assert d["recall"] == pytest.approx(0.75, abs=1e-4)
    assert d["f1"] == pytest.approx(0.6, abs=1e-4)


def test_compute_capability_metrics_known_counts():
    expected = [
        ("F1", "surgery"),       # -> SURGERY_GENERAL
        ("F2", "icu"),            # -> ICU
        ("F3", "dialysis"),       # -> DIALYSIS
        ("F4", "cardiology"),     # -> None (dropped from expected)
    ]
    predicted = [
        ("F1", CapabilityType.SURGERY_GENERAL),  # TP
        ("F2", CapabilityType.ICU),               # TP
        ("F3", CapabilityType.ONCOLOGY),          # FP (mismatch on F3)
        ("F4", CapabilityType.SURGERY_GENERAL),   # FP (F4 dropped from expected)
    ]
    m = compute_capability_metrics(expected, predicted)
    assert m.tp == 2
    assert m.fp == 2
    assert m.fn == 1  # F3 dialysis not predicted


def test_compute_capability_metrics_dedupes():
    expected = [("F1", "icu"), ("F1", "icu")]
    predicted = [("F1", CapabilityType.ICU), ("F1", CapabilityType.ICU)]
    m = compute_capability_metrics(expected, predicted)
    assert m.tp == 1 and m.fp == 0 and m.fn == 0


def test_compute_contradiction_metrics_restricts_to_universe():
    expected = [
        ("F1", "surgery", "capability_staff_mismatch"),  # positive
        ("F2", "icu", "none"),                            # negative
        ("F3", "dialysis", "vague_claim"),                # positive (unmapped type, still flagged)
        ("F4", "cardiology", "stale_or_weak_source"),     # dropped (cardiology unmapped)
    ]
    predicted = [
        ("F1", CapabilityType.SURGERY_GENERAL, ContradictionType.MISSING_STAFF),  # TP
        ("F2", CapabilityType.ICU, ContradictionType.MISSING_STAFF),  # FP
        # F3 dialysis: no predicted contradiction -> FN
        # F4 prediction below is filtered out (cardiology not in universe)
        ("F4", CapabilityType.MATERNAL, ContradictionType.STALE_DATA),
    ]
    m = compute_contradiction_metrics(expected, predicted)
    assert m.tp == 1
    assert m.fp == 1
    assert m.fn == 1
    # universe = 3 (F1, F2, F3), positives = 2 (F1, F3), predicted-in-universe = 2 (F1, F2)
    # TN = universe - pos - pred = {F2} - {F1,F2} = {} -> 0
    assert m.tn == 0


def test_compute_contradiction_metrics_all_clean():
    """Naomi sees no contradictions and the validator agrees -> precision/recall = 1.0."""
    expected = [("F1", "icu", "none"), ("F2", "surgery", "none")]
    predicted: list = []
    m = compute_contradiction_metrics(expected, predicted)
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0
    assert m.tn == 2
