"""Mocked unit tests for ``seahealth.db.databricks_resources``.

These tests must not make any live API calls. We monkeypatch
``get_workspace`` and the ``execute_sql`` helper so the orchestrator runs
purely against a recording mock.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from seahealth.db import databricks_resources as dr
from seahealth.db import sql_warehouse as sw

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def fake_workspace() -> MagicMock:
    """A WorkspaceClient mock with the surfaces ``databricks_resources`` touches."""
    ws = MagicMock(name="WorkspaceClient")

    # catalogs.list → returns workspace + system catalogs.
    workspace_cat = SimpleNamespace(
        name="workspace", catalog_type=SimpleNamespace(value="MANAGED_CATALOG")
    )
    system_cat = SimpleNamespace(
        name="system", catalog_type=SimpleNamespace(value="SYSTEM_CATALOG")
    )
    ws.catalogs.list.return_value = iter([system_cat, workspace_cat])

    # warehouses.list → one running warehouse.
    wh = SimpleNamespace(
        id="wh-test-1",
        name="Test Warehouse",
        state=SimpleNamespace(value="RUNNING"),
    )
    ws.warehouses.list.return_value = iter([wh])
    ws.warehouses.get.return_value = wh

    # volumes.read → not found by default; create succeeds.
    from databricks.sdk.errors import NotFound

    ws.volumes.read.side_effect = NotFound("volume not found")
    ws.volumes.create.return_value = SimpleNamespace(name="raw")

    # files.get_metadata → not found, so upload runs.
    ws.files.get_metadata.side_effect = NotFound("file not found")
    ws.files.upload.return_value = SimpleNamespace()

    # experiments: not-found path then create.
    ws.experiments.get_by_name.side_effect = NotFound("experiment not found")
    ws.experiments.create_experiment.return_value = SimpleNamespace(
        experiment_id="exp-123"
    )

    # vector search endpoint + index ops.
    ws.vector_search_endpoints.get_endpoint.side_effect = Exception("not found")
    ws.vector_search_endpoints.create_endpoint.return_value = SimpleNamespace()
    ws.vector_search_indexes.get_index.side_effect = Exception("not found")
    ws.vector_search_indexes.create_index.return_value = SimpleNamespace()
    return ws


@pytest.fixture
def patched_resources(monkeypatch, fake_workspace):
    """Patch :func:`get_workspace`, :func:`execute_sql`, :func:`ensure_running`.

    Returns the (workspace_mock, sql_calls_list) pair so individual tests can
    assert on what was issued.
    """
    sql_calls: list[str] = []

    def _record_sql(sql: str, *_, **__) -> list[dict]:
        sql_calls.append(sql)
        return []

    monkeypatch.setattr(dr, "get_workspace", lambda: fake_workspace)
    monkeypatch.setattr(dr, "execute_sql", _record_sql)
    monkeypatch.setattr(dr, "ensure_running", lambda *a, **kw: "wh-test-1")
    monkeypatch.setattr(dr, "get_warehouse_id", lambda: "wh-test-1")
    return fake_workspace, sql_calls


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def test_detect_catalog_prefers_workspace(patched_resources):
    """Without ``main`` available, ``workspace`` should win."""
    assert dr.detect_catalog() == "workspace"


def test_detect_catalog_falls_back_to_hive(monkeypatch, patched_resources):
    """When ``catalogs.list`` raises, return literal ``hive_metastore``."""
    fake_ws, _ = patched_resources
    fake_ws.catalogs.list.side_effect = RuntimeError("UC disabled")
    assert dr.detect_catalog() == "hive_metastore"


def test_ensure_schemas_issues_three_creates(patched_resources):
    """Bronze, silver, gold should each get a ``CREATE SCHEMA IF NOT EXISTS``."""
    _, sql_calls = patched_resources
    out = dr.ensure_schemas("workspace")
    assert out == {
        "bronze": "workspace.seahealth_bronze",
        "silver": "workspace.seahealth_silver",
        "gold": "workspace.seahealth_gold",
    }
    create_calls = [s for s in sql_calls if "CREATE SCHEMA" in s]
    assert len(create_calls) == 3
    for layer in ("seahealth_bronze", "seahealth_silver", "seahealth_gold"):
        assert any(layer in s for s in create_calls), f"missing CREATE for {layer}"


def test_ensure_schemas_rejects_unsafe_catalog(patched_resources):
    """Catalog names are interpolated into DDL, so reject unsafe identifiers."""
    _, sql_calls = patched_resources
    with pytest.raises(ValueError, match="invalid catalog"):
        dr.ensure_schemas("workspace;DROP")
    assert sql_calls == []


def test_ensure_volume_creates_when_not_found(patched_resources):
    """When ``volumes.read`` raises NotFound, ``volumes.create`` is invoked."""
    fake_ws, _ = patched_resources
    path = dr.ensure_volume("workspace")
    assert path == "/Volumes/workspace/seahealth_bronze/raw"
    fake_ws.volumes.create.assert_called_once()


def test_ensure_volume_skips_when_already_present(patched_resources):
    """When ``volumes.read`` succeeds, ``volumes.create`` must not be called."""
    fake_ws, _ = patched_resources
    fake_ws.volumes.read.side_effect = None
    fake_ws.volumes.read.return_value = SimpleNamespace(name="raw")
    dr.ensure_volume("workspace")
    fake_ws.volumes.create.assert_not_called()


def test_ensure_volume_returns_dbfs_path_when_no_uc(patched_resources):
    """``hive_metastore`` catalog → DBFS fallback path."""
    assert dr.ensure_volume("hive_metastore") == dr.DBFS_FALLBACK


def test_ensure_delta_tables_issues_seven_ddl_statements(patched_resources):
    """One ``CREATE TABLE`` per logical table; all fully-qualified names returned."""
    _, sql_calls = patched_resources
    names = dr.ensure_delta_tables(
        "workspace.seahealth_bronze",
        "workspace.seahealth_silver",
        "workspace.seahealth_gold",
    )
    assert len(names) == 7
    create_table_calls = [s for s in sql_calls if "CREATE TABLE" in s]
    assert len(create_table_calls) == 7
    expected_tables = {
        "facilities_raw", "chunks", "capabilities", "evidence_assessments",
        "contradictions", "facility_audits", "map_aggregates",
    }
    assert {n.rsplit(".", 1)[1] for n in names} == expected_tables


def test_ensure_delta_tables_rejects_unsafe_schema(patched_resources):
    """Fully-qualified schemas must stay in catalog.schema shape."""
    _, sql_calls = patched_resources
    with pytest.raises(ValueError, match="invalid bronze schema"):
        dr.ensure_delta_tables(
            "workspace.seahealth_bronze;DROP",
            "workspace.seahealth_silver",
            "workspace.seahealth_gold",
        )
    assert sql_calls == []


def test_upload_csv_replaces_partial_remote_file(patched_resources, tmp_path):
    """A stale/partial remote upload is deleted before replacement and verified."""
    fake_ws, _ = patched_resources
    csv = tmp_path / "vf.csv"
    csv.write_bytes(b"name\napollo\n")
    remote_path = "/Volumes/workspace/seahealth_bronze/raw/vf_hackathon_india.csv"

    metadata = [
        SimpleNamespace(content_length=3),
        SimpleNamespace(content_length=csv.stat().st_size),
    ]
    fake_ws.files.get_metadata.side_effect = metadata

    out = dr.upload_csv_to_volume(
        "/Volumes/workspace/seahealth_bronze/raw", local_csv_path=str(csv)
    )

    assert out == remote_path
    fake_ws.files.delete.assert_called_once_with(remote_path)
    fake_ws.files.upload.assert_called_once()


def test_upload_csv_cleans_partial_after_upload_error(patched_resources, tmp_path):
    """If upload fails and leaves a wrong-sized object, remove it for the next run."""
    fake_ws, _ = patched_resources
    csv = tmp_path / "vf.csv"
    csv.write_bytes(b"name\napollo\n")
    fake_ws.files.get_metadata.side_effect = [
        dr.NotFound("missing"),
        SimpleNamespace(content_length=2),
    ]
    fake_ws.files.upload.side_effect = RuntimeError("network reset")

    with pytest.raises(RuntimeError, match="network reset"):
        dr.upload_csv_to_volume(
            "/Volumes/workspace/seahealth_bronze/raw", local_csv_path=str(csv)
        )

    fake_ws.files.delete.assert_called_once()


def test_ensure_mlflow_experiment_creates_when_missing(patched_resources):
    fake_ws, _ = patched_resources
    exp_id = dr.ensure_mlflow_experiment()
    assert exp_id == "exp-123"
    fake_ws.experiments.create_experiment.assert_called_once()


def test_ensure_vector_search_returns_unavailable_on_failure(patched_resources):
    """If endpoint provisioning fails, status flips to 'unavailable'."""
    fake_ws, _ = patched_resources
    fake_ws.vector_search_endpoints.create_endpoint.side_effect = Exception(
        "vector search not enabled"
    )
    out = dr.ensure_vector_search(bronze="workspace.seahealth_bronze")
    assert out["status"] == "unavailable"
    assert out["fallback"] == "faiss"


def test_ensure_vector_search_rejects_unsafe_bronze_schema(patched_resources):
    with pytest.raises(ValueError, match="invalid bronze schema"):
        dr.ensure_vector_search(bronze="workspace.seahealth_bronze;DROP")


def test_ensure_vector_search_sets_current_delta_sync_fields(patched_resources):
    """The SDK spec should use text as embedding source and sync retriever columns."""
    fake_ws, _ = patched_resources
    out = dr.ensure_vector_search(bronze="workspace.seahealth_bronze")

    assert out["status"] == "ready"
    kwargs = fake_ws.vector_search_indexes.create_index.call_args.kwargs
    assert kwargs["primary_key"] == "chunk_id"
    spec = kwargs["delta_sync_index_spec"]
    assert spec.source_table == "workspace.seahealth_bronze.chunks"
    assert spec.columns_to_sync == ["chunk_id", "facility_id", "source_type", "text"]
    assert spec.embedding_source_columns[0].name == "text"
    assert (
        spec.embedding_source_columns[0].embedding_model_endpoint_name
        == "databricks-bge-large-en"
    )


def test_provision_all_orchestrates_in_order(monkeypatch, patched_resources, tmp_path):
    """End-to-end: every step gets called, return dict has all expected keys."""
    # Stub out CSV upload to avoid touching the filesystem path dance.
    csv = tmp_path / "vf.csv"
    csv.write_text("name,phone\nfoo,123\n", encoding="utf-8")

    monkeypatch.setattr(
        dr, "upload_csv_to_volume",
        lambda volume_path, local_csv_path=str(csv): f"{volume_path}/vf_hackathon_india.csv",
    )

    out = dr.provision_all(csv_path=str(csv), skip_vector_search=True)
    assert out["catalog"] == "workspace"
    assert out["schemas"] == {
        "bronze": "workspace.seahealth_bronze",
        "silver": "workspace.seahealth_silver",
        "gold": "workspace.seahealth_gold",
    }
    assert out["volume_path"].startswith("/Volumes/")
    assert out["csv_remote"].endswith("vf_hackathon_india.csv")
    assert len(out["tables"]) == 7
    assert out["mlflow_experiment_id"] == "exp-123"
    assert out["vector_search"]["status"] == "skipped"


def test_execute_sql_polls_and_returns_stable_chunked_rows(monkeypatch):
    ws = MagicMock(name="WorkspaceClient")
    monkeypatch.setattr(sw, "get_workspace", lambda: ws)
    monkeypatch.setattr(sw, "get_warehouse_id", lambda: "wh-test-1")
    monkeypatch.setattr(sw.time, "sleep", lambda *_: None)

    ws.statement_execution.execute_statement.return_value = SimpleNamespace(
        statement_id="stmt-1",
        status=SimpleNamespace(state="RUNNING"),
        manifest=None,
        result=None,
    )
    ws.statement_execution.get_statement.return_value = SimpleNamespace(
        status=SimpleNamespace(state="SUCCEEDED"),
        manifest=SimpleNamespace(
            schema=SimpleNamespace(
                columns=[SimpleNamespace(name="a"), SimpleNamespace(name="b")]
            )
        ),
        result=SimpleNamespace(data_array=[["one"]], next_chunk_index=1),
    )
    ws.statement_execution.get_statement_result_chunk_n.return_value = SimpleNamespace(
        data_array=[["two", "three", "extra"]],
        next_chunk_index=None,
    )

    assert sw.execute_sql("SELECT 1", wait_timeout_s=0) == [
        {"a": "one", "b": None},
        {"a": "two", "b": "three"},
    ]
    assert (
        ws.statement_execution.execute_statement.call_args.kwargs["wait_timeout"] == "0s"
    )


def test_execute_sql_redacts_bearer_tokens(monkeypatch):
    ws = MagicMock(name="WorkspaceClient")
    monkeypatch.setattr(sw, "get_workspace", lambda: ws)
    monkeypatch.setattr(sw, "get_warehouse_id", lambda: "wh-test-1")
    ws.statement_execution.execute_statement.return_value = SimpleNamespace(
        statement_id="stmt-1",
        status=SimpleNamespace(
            state="FAILED",
            error=SimpleNamespace(
                error_code="BAD",
                message="Authorization: Bearer secret-token-123",
            ),
        ),
        manifest=None,
        result=None,
    )

    with pytest.raises(RuntimeError) as excinfo:
        sw.execute_sql("SELECT 'Bearer query-token-456'")

    message = str(excinfo.value)
    assert "secret-token-123" not in message
    assert "query-token-456" not in message
    assert "Bearer [REDACTED]" in message
