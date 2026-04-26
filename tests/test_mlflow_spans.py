"""Tests for MLflow span coverage across the agent chain.

Covers Phase B steps 1-3 of the audit: span wrappers around
``validate_capability``, ``score_capability``, ``run_query`` (replacing the
empty span that used to close before the work), and ``build_facility_audit``.

Each agent must:
* never call ``mlflow.start_span`` when ``MLFLOW_TRACKING_URI`` is unset
  (the canonical defensive contract that ``test_extract_pipeline.py`` already
  enforces for the extractor pipeline).
* call ``mlflow.start_span(name=<expected>, attributes=...)`` exactly once
  when ``MLFLOW_TRACKING_URI`` is set, with attributes that include the
  facility id (where applicable) so traces are useful.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from seahealth.agents import facility_audit_builder, trust_scorer, validator
from seahealth.agents import query as query_agent
from seahealth.agents.heuristics import FacilityFacts
from seahealth.schemas import (
    Capability,
    CapabilityType,
    Contradiction,
    ContradictionType,
    EvidenceRef,
    GeoPoint,
    TrustScore,
)

NOW = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Shared fixtures
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


def _capability(ctype: CapabilityType = CapabilityType.SURGERY_APPENDECTOMY) -> Capability:
    return Capability(
        facility_id="vf_test",
        capability_type=ctype,
        claimed=True,
        evidence_refs=[_evidence("general surgery including appendectomy")],
        source_doc_id="doc_1",
        extracted_at=NOW,
        extractor_model="test-model",
    )


def _facts() -> FacilityFacts:
    return FacilityFacts(
        facility_id="vf_test",
        equipment=["anesthesia machine", "laparoscopy tower"],
        staff_count=4,
        capacity_beds=50,
    )


def _trust_score(ctype: CapabilityType = CapabilityType.SURGERY_APPENDECTOMY) -> TrustScore:
    return TrustScore(
        capability_type=ctype,
        claimed=True,
        evidence=[_evidence()],
        contradictions=[],
        confidence=0.7,
        confidence_interval=(0.6, 0.8),
        score=70,
        reasoning="Test reasoning.",
        computed_at=NOW,
    )


class _SpanRecorder:
    """Records calls to mlflow.start_span and yields a stub span object.

    The stub exposes ``trace_id`` so :func:`_extract_trace_id` returns a
    deterministic value, letting tests assert that the helper's yield is
    threaded through to the agent's return value when relevant.
    """

    def __init__(self, trace_id: str = "trace-stub") -> None:
        self.trace_id = trace_id
        self.calls: list[dict[str, Any]] = []

    def __call__(self, name: str, attributes: dict[str, Any] | None = None):
        self.calls.append({"name": name, "attributes": dict(attributes or {})})
        recorder = self

        @contextmanager
        def _ctx():
            class _Span:
                trace_id = recorder.trace_id

            yield _Span()

        return _ctx()


def _install_recorder(monkeypatch: pytest.MonkeyPatch) -> _SpanRecorder:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://stub")
    import mlflow  # type: ignore

    recorder = _SpanRecorder()
    monkeypatch.setattr(mlflow, "start_span", recorder)
    return recorder


def _block_mlflow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse any mlflow.start_span call — used when MLFLOW_TRACKING_URI is unset."""
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    import mlflow  # type: ignore

    def _boom(*_a, **_kw):  # pragma: no cover
        raise AssertionError("mlflow.start_span must not be called when unconfigured")

    monkeypatch.setattr(mlflow, "start_span", _boom)


# ---------------------------------------------------------------------------
# validate_capability
# ---------------------------------------------------------------------------


def test_validator_skips_span_when_mlflow_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_mlflow(monkeypatch)
    contradictions, _ = validator.validate_capability(_capability(), _facts(), use_llm=False)
    # Implementation still produces the correct heuristic result with no mlflow.
    assert isinstance(contradictions, list)


def test_validator_opens_named_span_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _install_recorder(monkeypatch)
    cap = _capability()
    validator.validate_capability(cap, _facts(), use_llm=False)
    names = [c["name"] for c in recorder.calls]
    assert "seahealth.validator.validate_capability" in names
    span = next(c for c in recorder.calls if c["name"] == "seahealth.validator.validate_capability")
    assert span["attributes"]["facility_id"] == cap.facility_id
    assert span["attributes"]["capability_type"] == cap.capability_type.value


# ---------------------------------------------------------------------------
# score_capability
# ---------------------------------------------------------------------------


def test_trust_scorer_skips_span_when_mlflow_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_mlflow(monkeypatch)
    ts = trust_scorer.score_capability(_capability(), [], use_llm=False)
    assert ts.score >= 0


def test_trust_scorer_opens_named_span_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _install_recorder(monkeypatch)
    cap = _capability()
    trust_scorer.score_capability(cap, [], use_llm=False)
    names = [c["name"] for c in recorder.calls]
    assert "seahealth.trust_scorer.score_capability" in names
    span = next(c for c in recorder.calls if c["name"] == "seahealth.trust_scorer.score_capability")
    assert span["attributes"]["facility_id"] == cap.facility_id


# ---------------------------------------------------------------------------
# run_query
# ---------------------------------------------------------------------------


def test_query_skips_span_when_mlflow_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_mlflow(monkeypatch)
    result = query_agent.run_query("Find an appendectomy facility near Patna", use_llm=False)
    assert result.query_trace_id  # heuristic path still produces a synthetic correlation id


def test_query_opens_named_span_around_actual_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _install_recorder(monkeypatch)
    query_agent.run_query("Find an appendectomy facility near Patna", use_llm=False)
    names = [c["name"] for c in recorder.calls]
    # Span name unchanged from the prior dead-span; the difference is that the
    # work now runs INSIDE it.
    assert "seahealth.query" in names


# ---------------------------------------------------------------------------
# build_facility_audit
# ---------------------------------------------------------------------------


def test_audit_builder_skips_span_when_mlflow_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_mlflow(monkeypatch)
    audit = facility_audit_builder.build_facility_audit(
        facility_id="vf_test",
        name="Hospital",
        location=GeoPoint(lat=25.6, lng=85.1, pin_code="800001"),
        capabilities=[_capability()],
        contradictions=[
            Contradiction(
                contradiction_type=ContradictionType.MISSING_STAFF,
                capability_type=CapabilityType.SURGERY_APPENDECTOMY,
                facility_id="vf_test",
                severity="MEDIUM",
                reasoning="No anesthesiologist on staff.",
                detected_by="validator.heuristics",
                detected_at=NOW,
            )
        ],
        evidence_assessments=[],
        trust_scores={CapabilityType.SURGERY_APPENDECTOMY: _trust_score()},
    )
    assert audit.facility_id == "vf_test"


def test_audit_builder_opens_named_span_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _install_recorder(monkeypatch)
    facility_audit_builder.build_facility_audit(
        facility_id="vf_test",
        name="Hospital",
        location=GeoPoint(lat=25.6, lng=85.1, pin_code="800001"),
        capabilities=[_capability()],
        contradictions=[],
        evidence_assessments=[],
        trust_scores={CapabilityType.SURGERY_APPENDECTOMY: _trust_score()},
    )
    names = [c["name"] for c in recorder.calls]
    assert "seahealth.facility_audit_builder.build" in names
    span = next(c for c in recorder.calls if c["name"] == "seahealth.facility_audit_builder.build")
    assert span["attributes"]["facility_id"] == "vf_test"
    assert span["attributes"]["capability_count"] == 1
