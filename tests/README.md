# SeaHealth tests

This directory holds the full pytest suite (246 tests). Tests are pure
Python — no live Anthropic, Databricks, or network calls. All LLM
interactions are mocked.

## Layout

| File | Owner | Surface under test |
|---|---|---|
| `test_imports.py` | smoke | top-level package re-exports |
| `test_schemas.py` | AUD-01 | every Pydantic model + invariants |
| `test_evidence_id.py` | AUD-01 | `evidence_ref_id()` helper |
| `test_extractor.py` | AUD-02 | LLM extractor (mocked Anthropic) |
| `test_validator.py` | AUD-02 | validator orchestration |
| `test_heuristics.py` | AUD-02 | heuristic detectors |
| `test_trust_scorer.py` | AUD-03 | trust-score derivation |
| `test_facility_audit_builder.py` | AUD-03 | per-facility audit assembly |
| `test_build_audits.py` | AUD-03/06 | parquet pipeline |
| `test_query.py` | AUD-04 | query agent (heuristic + tool loop) |
| `test_geocode.py` | AUD-04 | `INDIA_CITIES` + haversine |
| `test_tools.py` | AUD-04 | `tool_*` plain-Python tools |
| `test_databricks_resources.py` | AUD-05 | UC orchestration (mocked SDK) |
| `test_retriever.py` | AUD-05 | FAISS / TF / VS fallbacks |
| `test_normalize.py` | AUD-06 | CSV → chunks/facilities pipeline |
| `test_extract_pipeline.py` | AUD-06 | extract pipeline glue |
| `test_api.py` | AUD-07 | FastAPI in-process |
| `test_fixtures.py` | AUD-07 | fixture-vs-schema round-trips |
| `test_data_access.py` | AUD-07 | data layer (FIXTURE / PARQUET / DELTA) |
| `test_naomi_mapping.py` | AUD-eval | Naomi → internal taxonomy map |
| `test_eval_metrics.py` | AUD-eval | precision/recall conventions |
| `test_naomi_eval.py` | AUD-eval | full eval entrypoint |
| `fixtures/` | shared | golden inputs & expected outputs |

`conftest.py` and `_helpers.py` (this audit, AUD-08) are shared utilities;
no test cases live in them.

## Running tests

The shared venv is at `/Users/alejandro/Desktop/seahealth/.venv`.

```bash
# Whole suite
.venv/bin/pytest -q

# One file
.venv/bin/pytest tests/test_extractor.py -v

# Skip slow tests (e.g. bootstrap CI n>=200)
.venv/bin/pytest -m "not slow"

# Coverage gate
.venv/bin/coverage run -m pytest -q
.venv/bin/coverage report --skip-covered --skip-empty
```

## Using the helpers

The factories in `tests/_helpers.py` produce Pydantic-valid instances with
deterministic defaults. Any field can be overridden via kwargs:

```python
from tests._helpers import make_capability, make_contradiction, make_trust_score
from seahealth.schemas import CapabilityType, ContradictionType

cap = make_capability(
    facility_id="vf_demo",
    capability_type=CapabilityType.ICU,
)
contra = make_contradiction(
    facility_id=cap.facility_id,
    capability_type=cap.capability_type,
    contradiction_type=ContradictionType.MISSING_EQUIPMENT,
    severity="HIGH",
)
ts = make_trust_score(
    capability_type=cap.capability_type,
    contradictions=[contra],     # score auto-derived from formula
)
```

The score in `make_trust_score` is auto-derived from
`round(confidence*100) - severity_penalty`, so the resulting object always
satisfies the `TrustScore.model_validator`. Pass `score=...` explicitly to
test failure paths.

## Conftest behaviour

- Registers the `slow` marker (use `@pytest.mark.slow` on heavy tests).
- Resets `random` (and `numpy.random` if installed) to seed 0 before every test.
- Provides a session-scoped `repo_root` fixture.
- Strips `ANTHROPIC_API_KEY` from `os.environ` per test as a belt-and-braces
  guard against accidental live calls.

## Coverage gaps (audit snapshot, 2026-04-25)

Top 5 source modules under 80% line coverage:

| Module | Coverage | Notes |
|---|---|---|
| `seahealth/db/sql_warehouse.py` | 67% | polling/error branches |
| `seahealth/agents/validator.py` | 70% | LLM-prompt formatting branches |
| `seahealth/api/data_access.py` | 70% | DELTA mode tail-paths |
| `seahealth/db/databricks_resources.py` | 76% | error-path orchestration |
| `seahealth/agents/query.py` | 77% | LLM tool-loop edge cases |

Coverage on tests themselves is 99%+ across the suite.

## Tautology audit (read-only — list, don't fix)

These assertions verify that "the mock returned what the mock was
configured to return", which means they exercise the test scaffolding,
not the SUT. Owning AUD should consider replacing or augmenting them.

- `tests/test_extractor.py:120-127` — asserts the recorded `model`,
  `tool_choice`, `tools[0]['name']`, and the `system` prompt content. The
  fake just records the kwargs we passed; the assertion mostly proves the
  `_FakeMessages` recorder works. Useful only insofar as it pins the
  prompt-injection guard text.
- `tests/test_extractor.py:185-199` — `test_empty_chunks_returns_empty_no_llm_call`:
  asserts the fake client wasn't constructed; the test would still pass
  if the extractor short-circuited for any reason, not just empty input.
  Consider asserting `result.facility_id` and `result.capabilities == []`
  *and* the absence of any side effects on a real-shaped fake.
- `tests/test_validator.py:175-189` — `test_llm_path_adds_evidence_assessments_and_extra_contradiction`
  asserts that `len(client.calls) == 1` and that "Capability claim" appears
  in the prompt. Both are properties of the test's hand-built prompt
  template, not of any production behaviour.
- `tests/test_validator.py:224-247` — `test_llm_prompt_caps_long_snippets`:
  the assertion `long_snippet not in prompt` is correct, but the second
  assertion (`capped in prompt`) reproduces the same regex the SUT uses to
  cap snippets, so it cannot detect a regression in the cap algorithm.
- `tests/test_query.py:188-268` — `test_llm_path_with_mocked_tool_use`:
  the `len(calls) == 3` assertion and the verbatim re-derivation of the
  geocode input dictionary are tautological with the fake's structure. The
  ranked-facilities assertion is meaningful; the call-count one is not.
- `tests/test_databricks_resources.py:151-166` — `test_ensure_delta_tables_issues_seven_ddl_statements`:
  counts `CREATE TABLE` strings in the recorded SQL; this verifies the
  fake records SQL strings, not that the DDL is valid. Pair with a parser
  to detect smuggled keywords.
- `tests/test_databricks_resources.py:222-225` — `test_ensure_mlflow_experiment_creates_when_missing`:
  asserts `experiments.create_experiment.assert_called_once()`. The mock's
  side-effect is what makes the SUT take the create branch in the first
  place, so this is "the mock returned what the mock was configured to
  return". Strengthen by asserting on the experiment name passed.
- `tests/test_data_access.py:260-278` — `test_delta_mode_select_audits_uses_well_formed_sql`:
  the `assert "facility_id = ?" in sql` line passes regardless of what
  the cursor was given, because we control the cursor's `executed` list.
  This particular file already partially compensates by asserting on
  `params == [DEMO_FACILITY_ID]`, which is meaningful.

These are notes, not bugs — the AUD-08 fileScope is read-only on
`test_*.py`. The owning audits (AUD-02, AUD-04, AUD-05, AUD-07) can decide
whether to tighten or accept.
