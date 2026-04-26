"""Tests for the Query Agent's heuristic + LLM tool-loop entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seahealth.agents import llm_client, query
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


def test_query_returns_four_execution_steps(audits_parquet: str) -> None:
    """Phase 2: every successful run emits a four-step timeline."""
    result = query.run_query(
        "appendectomy near Patna",
        use_llm=False,
        audits_path=audits_parquet,
    )
    names = [step.name for step in result.execution_steps]
    assert names == ["parse_intent", "retrieve", "score", "rank"]
    # finished_at must not be before started_at for any step.
    for step in result.execution_steps:
        assert step.finished_at >= step.started_at


def test_query_mlflow_fields_none_without_tracking_uri(
    audits_parquet: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without MLFLOW_TRACKING_URI, mlflow fields are null and used_llm=False."""
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    result = query.run_query(
        "appendectomy near Patna",
        use_llm=False,
        audits_path=audits_parquet,
    )
    assert result.mlflow_trace_id is None
    assert result.mlflow_trace_url is None
    assert result.used_llm is False
    # The synthetic correlation id is always present and prefixed.
    assert result.query_trace_id.startswith("q_")


def test_query_retriever_mode_reports_faiss_local_by_default(
    audits_parquet: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When VS env vars are unset, retriever_mode is the local FAISS fallback."""
    monkeypatch.delenv("SEAHEALTH_VS_ENDPOINT", raising=False)
    monkeypatch.delenv("SEAHEALTH_VS_INDEX", raising=False)
    result = query.run_query(
        "appendectomy near Patna",
        use_llm=False,
        audits_path=audits_parquet,
    )
    assert result.retriever_mode == "faiss_local"


# ---------------------------------------------------------------------------
# Staffing qualifier — parsing + soft re-rank (MQ-1)
# ---------------------------------------------------------------------------


@pytest.fixture()
def equal_score_audits_parquet(tmp_path: Path) -> str:
    """Two facilities with IDENTICAL score / distance — qualifier is the only tiebreaker."""
    facilities = [
        {
            "facility_id": "vf_big_team",
            "name": "Big Team Hospital",
            "location": {"lat": 25.6121, "lng": 85.1418, "pin_code": "800001"},
            "trust_scores": {
                "SURGERY_APPENDECTOMY": _trust_score_dict(score=80, confidence=0.80)
            },
        },
        {
            "facility_id": "vf_small_team",
            "name": "Small Team Hospital",
            # Same lat/lng -> identical distance to query origin.
            "location": {"lat": 25.6121, "lng": 85.1418, "pin_code": "800001"},
            "trust_scores": {
                "SURGERY_APPENDECTOMY": _trust_score_dict(score=80, confidence=0.80)
            },
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
    path = tmp_path / "equal_score_audits.parquet"
    pq.write_table(table, path)
    return str(path)


def _write_facilities_index(
    tmp_path: Path, rows: list[tuple[str, int | None]]
) -> str:
    """Tiny helper: write a 2-column facilities_index.parquet for tests."""
    index_path = tmp_path / "facilities_index.parquet"
    pq.write_table(
        pa.table(
            {
                "facility_id": pa.array([r[0] for r in rows], type=pa.string()),
                "numberDoctors": pa.array([r[1] for r in rows], type=pa.int64()),
            }
        ),
        index_path,
    )
    return str(index_path)


@pytest.mark.parametrize(
    ("text", "expected_qualifier"),
    [
        (
            "Find a facility in rural Bihar that can perform an appendectomy "
            "and typically leverages parttime doctors near Patna",
            "parttime",
        ),
        ("Need a 24/7 emergency near Patna for appendectomy", "twentyfour_seven"),
        ("appendectomy near Patna", None),
        ("appendectomy near Patna with full-time staffing", "fulltime"),
        ("appendectomy near Patna at a small hospital", "low_volume"),
    ],
)
def test_heuristic_parses_staffing_qualifier(
    text: str, expected_qualifier: str | None, audits_parquet: str
) -> None:
    result = query.run_query(text, use_llm=False, audits_path=audits_parquet)
    assert result.parsed_intent.staffing_qualifier == expected_qualifier


def test_parttime_qualifier_promotes_small_team(
    equal_score_audits_parquet: str, tmp_path: Path
) -> None:
    """Two equal-score facilities — parttime qualifier surfaces the small-team one."""
    index_path = _write_facilities_index(
        tmp_path, [("vf_big_team", 25), ("vf_small_team", 3)]
    )

    # Baseline: no qualifier -> ordering is determined by trust + distance only,
    # which are equal here, so we just confirm both rows make it through.
    baseline = query.run_query(
        "appendectomy near Patna",
        use_llm=False,
        audits_path=equal_score_audits_parquet,
        facilities_index_path=index_path,
    )
    baseline_ids = [r.facility_id for r in baseline.ranked_facilities]
    assert set(baseline_ids) == {"vf_big_team", "vf_small_team"}

    # With "parttime doctors", the small team gets +5 boost and ranks first.
    promoted = query.run_query(
        "appendectomy near Patna staffed by parttime doctors",
        use_llm=False,
        audits_path=equal_score_audits_parquet,
        facilities_index_path=index_path,
    )
    assert promoted.parsed_intent.staffing_qualifier == "parttime"
    assert [r.facility_id for r in promoted.ranked_facilities] == [
        "vf_small_team",
        "vf_big_team",
    ]
    # Soft tiebreaker — raw trust scores remain unchanged on the model.
    assert {r.trust_score.score for r in promoted.ranked_facilities} == {80}


def test_parttime_qualifier_keeps_facilities_without_doctor_data(
    equal_score_audits_parquet: str, tmp_path: Path
) -> None:
    """A facility with NO numberDoctors row in the index must still appear in results."""
    # Only ONE of the two facilities has staffing data; the other is unknown.
    index_path = _write_facilities_index(
        tmp_path, [("vf_small_team", 3)]  # vf_big_team intentionally absent
    )
    result = query.run_query(
        "appendectomy near Patna staffed by parttime doctors",
        use_llm=False,
        audits_path=equal_score_audits_parquet,
        facilities_index_path=index_path,
    )
    ids = [r.facility_id for r in result.ranked_facilities]
    assert "vf_big_team" in ids, "missing staffing data must NOT drop a facility"
    assert "vf_small_team" in ids
    # The data-bearing match still gets boosted to rank 1.
    assert ids[0] == "vf_small_team"


def test_default_parsed_intent_has_no_staffing_qualifier(audits_parquet: str) -> None:
    """Backward-compat: ParsedIntent.staffing_qualifier defaults to None."""
    result = query.run_query(
        "appendectomy within 50 km of Patna",
        use_llm=False,
        audits_path=audits_parquet,
    )
    assert result.parsed_intent.staffing_qualifier is None


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

    monkeypatch.setattr(llm_client, "structured_call", fake_structured_call)

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

    monkeypatch.setattr(llm_client, "structured_call", fake_structured_call)

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
