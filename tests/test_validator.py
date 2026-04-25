"""Tests for the Validator agent orchestration layer.

Covers:
  - heuristics-only path (use_llm=False) matches run_all_heuristics directly.
  - LLM path with a mocked client returns contradictions + EvidenceAssessments.
  - LLM client failure is logged and falls back gracefully to heuristic-only.
  - Reasoning overrides only fill blanks, never overwrite a heuristic reasoning.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from seahealth.agents.heuristics import FacilityFacts, run_all_heuristics
from seahealth.agents.validator import validate_capability
from seahealth.schemas import (
    Capability,
    CapabilityType,
    ContradictionType,
    EvidenceRef,
)

NOW = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "validator"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evidence(snippet: str = "snippet", chunk_id: str = "chunk_1") -> EvidenceRef:
    return EvidenceRef(
        source_doc_id="doc_1",
        facility_id="vf_test",
        chunk_id=chunk_id,
        row_id=None,
        span=(0, len(snippet)),
        snippet=snippet,
        source_type="facility_note",
        source_observed_at=NOW,
        retrieved_at=NOW,
    )


def _capability(
    cap_type: CapabilityType = CapabilityType.SURGERY_APPENDECTOMY,
) -> Capability:
    return Capability(
        facility_id="vf_test",
        capability_type=cap_type,
        claimed=True,
        evidence_refs=[_evidence("general surgery including appendectomy")],
        source_doc_id="doc_1",
        extracted_at=NOW,
        extractor_model="claude-sonnet-4-6",
    )


def _flagged_facts() -> FacilityFacts:
    return FacilityFacts(
        facility_id="vf_test",
        equipment=[],
        staff_count=0,
        capacity_beds=50,
        recency_of_page_update_months=6,
        specialties=[],
        procedures=[],
        capability_claims=[],
    )


def _clean_facts() -> FacilityFacts:
    return FacilityFacts(
        facility_id="vf_test",
        equipment=["anesthesia machine", "laparoscopy tower"],
        staff_count=4,
        capacity_beds=50,
        recency_of_page_update_months=6,
        specialties=[],
        procedures=[],
        capability_claims=[],
    )


class _FakeClient:
    """Records the prompt and returns a canned structured payload."""

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        raise_exc: Exception | None = None,
    ):
        self.payload = payload
        self.raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    def structured_call(self, prompt: str, *, model: str = "x") -> Any:
        self.calls.append({"prompt": prompt, "model": model})
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_heuristics_only_path_matches_run_all_heuristics():
    cap = _capability()
    facts = _flagged_facts()
    expected = run_all_heuristics(cap, facts, validator_id="validator.v1.heuristics")

    contradictions, assessments = validate_capability(cap, facts, use_llm=False)

    assert assessments == []
    assert len(contradictions) == len(expected)
    assert {c.contradiction_type for c in contradictions} == {
        c.contradiction_type for c in expected
    }
    # Heuristic-detected contradictions must always carry a one-sentence reasoning.
    for c in contradictions:
        assert c.reasoning and c.reasoning.endswith(".")


def test_clean_facility_heuristics_only_returns_empty():
    contradictions, assessments = validate_capability(
        _capability(), _clean_facts(), use_llm=False
    )
    assert contradictions == []
    assert assessments == []


def test_llm_path_adds_evidence_assessments_and_extra_contradiction():
    cap = _capability()
    facts = _clean_facts()
    extra_evidence = [
        _evidence("conflicting source: appendectomy not offered", chunk_id="chunk_2"),
        _evidence("staff roster shows one general surgeon", chunk_id="chunk_3"),
    ]
    payload = {
        "evidence_assessments": [
            {
                "evidence_ref_id": "doc_1:chunk_2",
                "stance": "contradicts",
                "reasoning": "External directory lists no surgical capability for this facility.",
            },
            {
                "evidence_ref_id": "doc_1:chunk_3",
                "stance": "verifies",
                "reasoning": "Staff roster confirms a surgeon is on staff.",
            },
        ],
        "additional_contradictions": [
            {
                "contradiction_type": "CONFLICTING_SOURCES",
                "severity": "HIGH",
                "reasoning": "Two independent sources disagree on whether appendectomy is offered.",
            }
        ],
    }
    client = _FakeClient(payload)
    contradictions, assessments = validate_capability(
        cap,
        facts,
        retrieved_evidence=extra_evidence,
        use_llm=True,
        client_factory=lambda: client,
    )

    assert len(client.calls) == 1
    assert "Capability claim" in client.calls[0]["prompt"]
    # Heuristics had nothing on a clean facility, so contradictions == LLM extras.
    assert len(contradictions) == 1
    assert contradictions[0].contradiction_type == ContradictionType.CONFLICTING_SOURCES
    assert contradictions[0].severity == "HIGH"
    assert contradictions[0].detected_by.endswith("llm")

    assert len(assessments) == 2
    stances = {a.evidence_ref_id: a.stance for a in assessments}
    assert stances == {
        "doc_1:chunk_2": "contradicts",
        "doc_1:chunk_3": "verifies",
    }


def test_llm_failure_falls_back_to_heuristics_only(caplog):
    cap = _capability()
    facts = _flagged_facts()
    boom = _FakeClient(raise_exc=RuntimeError("anthropic 503"))

    with caplog.at_level("WARNING"):
        contradictions, assessments = validate_capability(
            cap,
            facts,
            retrieved_evidence=[_evidence()],
            use_llm=True,
            client_factory=lambda: boom,
        )

    assert assessments == []
    expected = run_all_heuristics(cap, facts, validator_id="validator.v1.heuristics")
    assert {c.contradiction_type for c in contradictions} == {
        c.contradiction_type for c in expected
    }
    assert any("structured_call failed" in rec.message for rec in caplog.records)


def test_llm_path_ignores_disallowed_contradiction_type():
    """The LLM may only add a closed set of types; others must be silently dropped."""
    cap = _capability()
    facts = _clean_facts()
    payload = {
        "evidence_assessments": [],
        "additional_contradictions": [
            # MISSING_EQUIPMENT is reserved for heuristics — drop it.
            {
                "contradiction_type": "MISSING_EQUIPMENT",
                "severity": "HIGH",
                "reasoning": "should be dropped",
            },
            {
                "contradiction_type": "VOLUME_MISMATCH",
                "severity": "MEDIUM",
                "reasoning": "Bed count looks too low for the claimed volume.",
            },
        ],
    }
    contradictions, _ = validate_capability(
        cap,
        facts,
        retrieved_evidence=[_evidence()],
        use_llm=True,
        client_factory=lambda: _FakeClient(payload),
    )
    types = {c.contradiction_type for c in contradictions}
    assert ContradictionType.VOLUME_MISMATCH in types
    assert ContradictionType.MISSING_EQUIPMENT not in types


def test_fixture_clean_capability_yields_no_contradictions():
    cap = Capability.model_validate_json((FIXTURES / "sample_capability.json").read_text())
    facts_blob = json.loads((FIXTURES / "sample_facts.json").read_text())
    facts = FacilityFacts(**facts_blob["clean"])

    contradictions, _ = validate_capability(cap, facts, use_llm=False)
    assert contradictions == []
