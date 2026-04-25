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
