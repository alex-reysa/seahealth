"""Tests for the Query Agent's heuristic + LLM tool-loop entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seahealth.agents import anthropic_client, query
from seahealth.schemas import CapabilityType

# ---------------------------------------------------------------------------
# Helpers + fixtures
# ---------------------------------------------------------------------------


def _trust_score_dict(score: int, confidence: float, evidence: int = 1) -> dict:
    return {
        "capability_type": "SURGERY_APPENDECTOMY",
        "claimed": True,
        "evidence": [
            {
                "source_doc_id": f"doc_{i}",
                "facility_id": "vf_test",
                "chunk_id": f"chunk_{i}",
                "row_id": None,
                "span": [0, 5],
                "snippet": "snip",
                "source_type": "facility_note",
                "source_observed_at": "2026-01-01T00:00:00Z",
                "retrieved_at": "2026-04-25T18:00:00Z",
            }
            for i in range(evidence)
        ],
        "contradictions": [],
        "confidence": confidence,
        "confidence_interval": [max(0.0, confidence - 0.05), min(1.0, confidence + 0.02)],
        "score": score,
        "reasoning": "test",
        "computed_at": "2026-04-25T18:00:00Z",
    }


@pytest.fixture()
def audits_parquet(tmp_path: Path) -> str:
    facilities = [
        {
            "facility_id": "vf_near_patna",
            "name": "Patna Central",
            "location": {"lat": 25.6121, "lng": 85.1418, "pin_code": "800001"},
            "trust_scores": {
                "SURGERY_APPENDECTOMY": _trust_score_dict(score=88, confidence=0.88, evidence=2)
            },
        },
        {
            "facility_id": "vf_bihta",
            "name": "Bihta District Hospital",
            "location": {"lat": 25.5639, "lng": 84.8651, "pin_code": "801103"},
            "trust_scores": {"SURGERY_APPENDECTOMY": _trust_score_dict(score=70, confidence=0.70)},
        },
    ]
    table = pa.table(
        {
            "facility_id": [f["facility_id"] for f in facilities],
            "name": [f["name"] for f in facilities],
            "location": [json.dumps(f["location"]) for f in facilities],
            "trust_scores": [json.dumps(f["trust_scores"]) for f in facilities],
        }
    )
    path = tmp_path / "facility_audits.parquet"
    pq.write_table(table, path)
    return str(path)


# ---------------------------------------------------------------------------
# Heuristic path
# ---------------------------------------------------------------------------


def test_heuristic_appendectomy_query(audits_parquet: str) -> None:
    result = query.run_query(
        "Which facilities within 50km of Patna can perform an appendectomy?",
        use_llm=False,
        audits_path=audits_parquet,
    )
    assert result.parsed_intent.capability_type is CapabilityType.SURGERY_APPENDECTOMY
    assert result.parsed_intent.location.pin_code == "800001"
    assert result.parsed_intent.radius_km == 50.0
    assert result.total_candidates >= 1
    assert len(result.ranked_facilities) >= 1
    assert result.ranked_facilities[0].rank == 1


@pytest.mark.parametrize(
    ("text", "expected_radius"),
    [
        ("appendectomy within 50 km of Patna", 50.0),
        ("appendectomy within 50km of Patna", 50.0),
        ("appendectomy near Patna, 50 km radius", 50.0),
        ("appendectomy within fifty km of Patna", 50.0),
        ("appendectomy near Patna, fifty km radius", 50.0),
    ],
)
def test_heuristic_radius_patterns(text: str, expected_radius: float, audits_parquet: str) -> None:
    result = query.run_query(text, use_llm=False, audits_path=audits_parquet)
    assert result.parsed_intent.radius_km == expected_radius


@pytest.mark.parametrize(
    ("text", "expected_capability"),
    [
        ("appendicitis care near Patna", CapabilityType.SURGERY_APPENDECTOMY),
        ("appendix removal near Patna", CapabilityType.SURGERY_APPENDECTOMY),
        ("appendix surgery near Patna", CapabilityType.SURGERY_APPENDECTOMY),
        ("abdominal surgery near Patna", CapabilityType.SURGERY_GENERAL),
    ],
)
def test_heuristic_surgery_synonyms(
    text: str, expected_capability: CapabilityType, audits_parquet: str
) -> None:
    result = query.run_query(text, use_llm=False, audits_path=audits_parquet)
    assert result.parsed_intent.capability_type is expected_capability


def test_heuristic_radius_default(audits_parquet: str) -> None:
    """No explicit radius in the query -> default of 50 km."""
    result = query.run_query(
        "appendectomy near Patna",
        use_llm=False,
        audits_path=audits_parquet,
    )
    assert result.parsed_intent.radius_km == query.DEFAULT_RADIUS_KM == 50.0


def test_query_no_match_returns_empty_result(audits_parquet: str) -> None:
    """Unknown city geocodes to None -> empty ranked_facilities, total 0."""
    result = query.run_query(
        "appendectomy near Atlantis",
        use_llm=False,
        audits_path=audits_parquet,
    )
    assert result.ranked_facilities == []
    assert result.total_candidates == 0


def test_query_empty_candidate_state_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing.parquet"
    result = query.run_query(
        "appendectomy within 50 km of Patna",
        use_llm=False,
        audits_path=str(missing),
    )
    assert result.ranked_facilities == []
    assert result.total_candidates == 0


def test_query_trace_id_present(audits_parquet: str) -> None:
    result = query.run_query(
        "appendectomy near Patna",
        use_llm=False,
        audits_path=audits_parquet,
    )
    assert result.query_trace_id
    assert result.query_trace_id.startswith("q_")


# ---------------------------------------------------------------------------
# LLM tool-loop path (mocked)
# ---------------------------------------------------------------------------


class _FakeBlock:
    def __init__(self, *, type_: str, **kwargs: Any) -> None:
        self.type = type_
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeMessage:
    def __init__(self, blocks: list[Any]) -> None:
        self.content = blocks


def test_llm_path_with_mocked_tool_use(
    audits_parquet: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive a 2-step tool loop: geocode -> search_facilities -> emit_QueryPlan."""
    calls: list[dict] = []

    # Three responses, returned in order on successive structured_call invocations.
    response_steps = [
        _FakeMessage(
            [
                _FakeBlock(
                    type_="tool_use",
                    id="t1",
                    name="geocode",
                    input={"query": "Patna"},
                )
            ]
        ),
        _FakeMessage(
            [
                _FakeBlock(
                    type_="tool_use",
                    id="t2",
                    name="search_facilities",
                    input={
                        "capability_type": "SURGERY_APPENDECTOMY",
                        "lat": 25.61,
                        "lng": 85.14,
                        "radius_km": 50.0,
                    },
                )
            ]
        ),
        _FakeMessage(
            [
                _FakeBlock(
                    type_="tool_use",
                    id="t3",
                    name="emit_QueryPlan",
                    input={
                        "capability_type": "SURGERY_APPENDECTOMY",
                        "location": {
                            "lat": 25.61,
                            "lng": 85.14,
                            "pin_code": "800001",
                        },
                        "radius_km": 50.0,
                        "selected_facility_ids": ["vf_bihta", "vf_near_patna"],
                    },
                )
            ]
        ),
    ]
    iter_steps = iter(response_steps)

    def fake_structured_call(**kwargs: Any) -> Any:
        calls.append(kwargs)
        try:
            return next(iter_steps)
        except StopIteration as exc:  # pragma: no cover - guard
            raise AssertionError("structured_call invoked too many times") from exc

    monkeypatch.setattr(anthropic_client, "structured_call", fake_structured_call)

    result = query.run_query(
        "Which facilities within 50km of Patna can perform an appendectomy?",
        use_llm=True,
        max_steps=6,
        retries=1,
        audits_path=audits_parquet,
    )

    assert len(calls) == 3
    assert result.parsed_intent.capability_type is CapabilityType.SURGERY_APPENDECTOMY
    assert result.parsed_intent.location.pin_code == "800001"
    assert result.parsed_intent.radius_km == 50.0
    assert result.query_trace_id.startswith("q_")
    assert len(result.ranked_facilities) >= 1
    # Deterministic ranking wins over the model's selected id order.
    assert result.ranked_facilities[0].facility_id == "vf_near_patna"
    assert result.ranked_facilities[0].rank == 1


def test_llm_path_max_steps_guard_falls_back(
    audits_parquet: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    def fake_structured_call(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return _FakeMessage(
            [
                _FakeBlock(
                    type_="tool_use",
                    id=f"t{len(calls)}",
                    name="geocode",
                    input={"query": "Patna"},
                )
            ]
        )

    monkeypatch.setattr(anthropic_client, "structured_call", fake_structured_call)

    result = query.run_query(
        "Which facilities within 50km of Patna can perform an appendectomy?",
        use_llm=True,
        max_steps=2,
        retries=1,
        audits_path=audits_parquet,
    )

    assert len(calls) == 2
    assert result.parsed_intent.capability_type is CapabilityType.SURGERY_APPENDECTOMY
    assert result.ranked_facilities
