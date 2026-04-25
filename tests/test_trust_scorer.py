"""Tests for ``seahealth.agents.trust_scorer``.

The scorer is fully deterministic given the same ``rng_seed``; these tests pin
the recipe and the band mapping (green ≥80, amber 50-79, red 0-49) against
the hand-crafted scenarios in ``tests/fixtures/trust/sample_inputs.json``.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from seahealth.agents.trust_scorer import score_capability
from seahealth.schemas import (
    Capability,
    CapabilityType,
    Contradiction,
    ContradictionType,
    EvidenceRef,
    TrustScore,
)

FIXTURES = Path(__file__).parent / "fixtures" / "trust" / "sample_inputs.json"
NOW = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixtures() -> dict[str, Any]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def _capability_from(blob: dict[str, Any]) -> Capability:
    return Capability.model_validate(blob)


def _contradictions_from(blobs: list[dict[str, Any]]) -> list[Contradiction]:
    return [Contradiction.model_validate(b) for b in blobs]


def _evidence(
    snippet: str = "snippet",
    chunk_id: str = "chunk_1",
    source_type: str = "facility_note",
) -> EvidenceRef:
    return EvidenceRef(
        source_doc_id="doc_x",
        facility_id="vf_00042_janta_hospital_patna",
        chunk_id=chunk_id,
        row_id=None,
        span=(0, len(snippet)),
        snippet=snippet,
        source_type=source_type,  # type: ignore[arg-type]
        source_observed_at=NOW,
        retrieved_at=NOW,
    )


def _capability(
    cap_type: CapabilityType = CapabilityType.SURGERY_APPENDECTOMY,
    n_evidence: int = 1,
    distinct_types: int = 1,
) -> Capability:
    types = ["facility_note", "staff_roster", "equipment_inventory", "volume_report"]
    refs: list[EvidenceRef] = []
    for i in range(n_evidence):
        refs.append(
            _evidence(
                snippet=f"snippet {i}",
                chunk_id=f"chunk_{i}",
                source_type=types[i % distinct_types],
            )
        )
    return Capability(
        facility_id="vf_00042_janta_hospital_patna",
        capability_type=cap_type,
        claimed=True,
        evidence_refs=refs,
        source_doc_id="doc_x",
        extracted_at=NOW,
        extractor_model="claude-sonnet-4-6",
    )


def _contradiction(
    severity: str = "HIGH",
    contradiction_type: ContradictionType | None = None,
) -> Contradiction:
    return Contradiction(
        contradiction_type=contradiction_type or ContradictionType.MISSING_STAFF,
        capability_type=CapabilityType.SURGERY_APPENDECTOMY,
        facility_id="vf_00042_janta_hospital_patna",
        evidence_for=[],
        evidence_against=[],
        severity=severity,  # type: ignore[arg-type]
        reasoning="test reason.",
        detected_by="validator.test",
        detected_at=NOW,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_deterministic_score_formula_matches_contract():
    """Score = clamp(round(confidence*100) - severity_sum, 0, 100)."""
    cap = _capability(n_evidence=3, distinct_types=3)  # confidence = 0.95
    contradictions = [_contradiction("HIGH"), _contradiction("MEDIUM")]
    ts = score_capability(cap, contradictions, use_llm=False)

    # 95 - (30 + 15) = 50
    assert ts.score == 50
    assert ts.confidence == pytest.approx(0.95)
    assert isinstance(ts, TrustScore)


def test_zero_evidence_claim_has_minimum_confidence_and_collapsed_ci():
    cap = _capability(n_evidence=0, distinct_types=1)
    ts = score_capability(cap, [], use_llm=False)

    assert ts.confidence == pytest.approx(0.05)
    assert ts.score == 5
    assert ts.confidence_interval == (ts.confidence, ts.confidence)
    assert "no contradictions" in ts.reasoning


def test_templated_reasoning_names_contradiction_types():
    cap = _capability(n_evidence=1, distinct_types=1)
    contradictions = [
        _contradiction("LOW", ContradictionType.STALE_DATA),
        _contradiction("HIGH", ContradictionType.MISSING_EQUIPMENT),
    ]
    ts = score_capability(cap, contradictions, use_llm=False)

    assert "MISSING_EQUIPMENT" in ts.reasoning
    assert "STALE_DATA" in ts.reasoning


def test_rng_seed_yields_reproducible_confidence_interval():
    cap = _capability(n_evidence=2, distinct_types=2)
    contradictions = [_contradiction("MEDIUM"), _contradiction("LOW")]

    a = score_capability(cap, contradictions, use_llm=False, rng_seed=7)
    b = score_capability(cap, contradictions, use_llm=False, rng_seed=7)

    assert a.score == b.score
    assert a.confidence == b.confidence
    assert round(a.confidence_interval[0], 4) == round(b.confidence_interval[0], 4)
    assert round(a.confidence_interval[1], 4) == round(b.confidence_interval[1], 4)


def test_clean_fixture_lands_in_green_band():
    fixtures = _load_fixtures()
    cap = _capability_from(fixtures["clean"]["capability"])
    contradictions = _contradictions_from(fixtures["clean"]["contradictions"])
    ts = score_capability(cap, contradictions, use_llm=False)

    assert ts.score == fixtures["clean"]["expected_score"] == 95
    lo, hi = fixtures["clean"]["expected_score_band"]
    assert lo <= ts.score <= hi


def test_flagged_fixture_lands_in_red_band():
    fixtures = _load_fixtures()
    cap = _capability_from(fixtures["flagged"]["capability"])
    contradictions = _contradictions_from(fixtures["flagged"]["contradictions"])
    ts = score_capability(cap, contradictions, use_llm=False)

    assert ts.score == fixtures["flagged"]["expected_score"] == 35
    lo, hi = fixtures["flagged"]["expected_score_band"]
    assert lo <= ts.score <= hi


def test_mixed_fixture_lands_in_amber_band():
    fixtures = _load_fixtures()
    cap = _capability_from(fixtures["mixed"]["capability"])
    contradictions = _contradictions_from(fixtures["mixed"]["contradictions"])
    ts = score_capability(cap, contradictions, use_llm=False)

    assert ts.score == fixtures["mixed"]["expected_score"] == 60
    lo, hi = fixtures["mixed"]["expected_score_band"]
    assert lo <= ts.score <= hi


def test_llm_path_uses_client_factory_reasoning():
    cap = _capability(n_evidence=2, distinct_types=2)
    contradictions: list[Contradiction] = []
    canned = "Verified: appendectomy capability supported by anesthesia + surgeon evidence."

    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def structured_call(self, prompt: str, *, model: str = "x") -> str:
            self.calls.append({"prompt": prompt, "model": model})
            return canned

    client = _FakeClient()
    ts = score_capability(
        cap,
        contradictions,
        use_llm=True,
        client_factory=lambda: client,
    )

    assert ts.reasoning == canned
    assert client.calls and "Capability" in client.calls[0]["prompt"]


def test_llm_factory_failure_falls_back_to_templated_reasoning(caplog):
    cap = _capability(n_evidence=1, distinct_types=1)
    contradictions: list[Contradiction] = []

    def _factory():
        raise RuntimeError("boom")

    with caplog.at_level("WARNING"):
        ts = score_capability(
            cap,
            contradictions,
            use_llm=True,
            client_factory=_factory,
        )

    # Templated reasoning shape is documented in the trust_scorer module.
    assert ts.reasoning.startswith(f"Score {ts.score} based on")
    assert any("client_factory raised" in rec.message for rec in caplog.records)


def test_llm_structured_call_failure_falls_back_to_templated_reasoning(caplog):
    cap = _capability(n_evidence=1, distinct_types=1)
    contradictions: list[Contradiction] = []

    class _Boom:
        def structured_call(self, prompt: str, *, model: str = "x") -> str:
            raise RuntimeError("503")

    with caplog.at_level("WARNING"):
        ts = score_capability(
            cap,
            contradictions,
            use_llm=True,
            client_factory=lambda: _Boom(),
        )

    assert ts.reasoning.startswith(f"Score {ts.score} based on")
    assert any("structured_call failed" in rec.message for rec in caplog.records)
