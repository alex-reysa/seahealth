"""Smoke tests for the scoring half of the Layer-2 pipeline.

The data-loading half (load_nfhs, pivot, code-based join) is exercised against
real inputs in interactive verification; this file pins the scoring path
behind synthetic fixtures so a CI run catches regressions in:

  - compute_coverage_quality (BallTree + trust weighting)
  - compute_need_index_proxy (SBA + Institutional Births + ANC4+)
  - compute_desert_score
  - assign_risk_tier

Run from this directory: python -m pytest test_smoke.py
Or: python test_smoke.py (calls main() below).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import desert_score_model as m


def test_compute_coverage_quality_basic() -> None:
    """Two districts; three facilities. District 0 has two facilities within
    30 km (one supports, one unclear with a contradiction). District 1 has
    none in range."""
    district_lats = np.array([10.0, 20.0])
    district_lons = np.array([75.0, 80.0])
    fac_lats = np.array([10.0, 10.05, 25.0])
    fac_lons = np.array([75.0, 75.05, 85.0])
    fac_weights = np.array([1.0, 0.5, 1.0])
    fac_trust = np.array(["supports", "unclear", "supports"], dtype=object)
    fac_contradiction = np.array(["", "MISSING_STAFF", ""], dtype=object)

    cov, raw_sum, verified, contradictions = m.compute_coverage_quality(
        district_lats, district_lons,
        fac_lats, fac_lons,
        fac_weights, fac_trust, fac_contradiction,
        radius_km=30,
    )

    assert cov.shape == (2,)
    assert raw_sum[0] > 0, "district 0 should have non-zero raw_sum"
    assert raw_sum[1] == 0, "district 1 should have no nearby facilities"
    assert verified[0] == 1, "one 'supports' facility within 30km of district 0"
    assert verified[1] == 0
    assert contradictions[0] == "MISSING_STAFF"
    assert contradictions[1] == ""
    # Coverage quality is raw_sum / saturation, capped at 1.0
    assert 0.0 < cov[0] <= 1.0
    assert cov[1] == 0.0


def test_compute_coverage_quality_empty_facilities() -> None:
    """No facilities at all -> all-zero outputs of the right shape."""
    cov, raw_sum, verified, contradictions = m.compute_coverage_quality(
        district_lats=np.array([10.0, 20.0]),
        district_lons=np.array([75.0, 80.0]),
        facility_lats=np.array([]),
        facility_lons=np.array([]),
        facility_weights=np.array([]),
        facility_trust_score=np.array([], dtype=object),
        facility_contradiction_type=np.array([], dtype=object),
        radius_km=30,
    )
    assert cov.shape == (2,) and (cov == 0).all()
    assert raw_sum.shape == (2,) and (raw_sum == 0).all()
    assert verified.shape == (2,) and (verified == 0).all()
    assert contradictions == ["", ""]


def test_proxy_need_index_monotonic_and_bounded() -> None:
    sba  = pd.Series([90.0, 50.0, 0.0])
    inst = pd.Series([90.0, 50.0, 0.0])
    anc  = pd.Series([90.0, 50.0, 0.0])
    proxy = m.compute_need_index_proxy(sba, inst, anc)

    assert (proxy >= 0).all()
    assert (proxy <= 100).all()
    # Lower coverage -> higher need
    assert proxy.iloc[0] < proxy.iloc[1] < proxy.iloc[2]
    # All gaps = 10% -> 100 * (0.5*0.1 + 0.3*0.1 + 0.2*0.1) = 10
    assert abs(proxy.iloc[0] - 10.0) < 1e-9
    # All gaps = 100% -> 100
    assert abs(proxy.iloc[2] - 100.0) < 1e-9


def test_proxy_need_index_clips_out_of_range() -> None:
    """Bad upstream values (>100, <0) should not blow up the formula."""
    proxy = m.compute_need_index_proxy(
        pd.Series([150.0, -10.0, 100.0]),
        pd.Series([100.0,  50.0, 100.0]),
        pd.Series([100.0,  50.0, 100.0]),
    )
    assert (proxy >= 0).all()
    assert (proxy <= 100).all()


def test_desert_score_and_risk_tiers() -> None:
    need = np.array([5.0, 20.0, 50.0, 80.0, 100.0])
    cov  = np.array([1.0, 0.5,  0.1,  0.05, 0.0])
    scores = m.compute_desert_score(need, cov)
    tiers = m.assign_risk_tier(scores)

    assert tiers.shape == (5,)
    # Strictly increasing need with strictly decreasing coverage
    # -> strictly increasing desert scores
    assert (np.diff(scores) > 0).all()
    # The worst row should land in the top tier; the best in the bottom.
    assert tiers[-1] == "critical"
    assert tiers[0] == "low"


def test_assign_risk_tier_handles_empty_or_all_nan() -> None:
    out = m.assign_risk_tier(np.array([]))
    assert out.shape == (0,)

    out_nan = m.assign_risk_tier(np.array([np.nan, np.nan, np.nan]))
    # All-NaN should fall through to "low" (safe default per docstring)
    assert (out_nan == "low").all()


def test_trust_weight_ordering() -> None:
    """Trust weights must be strictly ordered: supports > unclear > contradicts > silent."""
    w = m.TRUST_WEIGHTS
    assert w["supports"] > w["unclear"] > w["contradicts"] > w["silent"]
    assert w["supports"] == 1.0
    assert w["silent"] >= 0.0


def test_neonatal_relevance_substring_match() -> None:
    """The token detector should fire on common neonatal/maternity strings."""
    assert m.is_neonatal_relevant("NICU, Level III", "neonatal critical care")
    assert m.is_neonatal_relevant(["Pediatrics"], "")
    assert m.is_neonatal_relevant("", "Maternity ward")
    assert not m.is_neonatal_relevant("Cardiology", "Adult ICU")
    assert not m.is_neonatal_relevant(None, None)


def main() -> int:
    """Allow `python test_smoke.py` to run without pytest installed."""
    tests = [
        test_compute_coverage_quality_basic,
        test_compute_coverage_quality_empty_facilities,
        test_proxy_need_index_monotonic_and_bounded,
        test_proxy_need_index_clips_out_of_range,
        test_desert_score_and_risk_tiers,
        test_assign_risk_tier_handles_empty_or_all_nan,
        test_trust_weight_ordering,
        test_neonatal_relevance_substring_match,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
