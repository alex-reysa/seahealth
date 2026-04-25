# Databricks Provisioning

This document covers the SeaHealth Databricks foundation: schemas, volumes,
Delta tables, MLflow, and Vector Search. Everything is provisioned by a single
idempotent script — re-running it is always safe.

## Quick start

From the worktree root with the project venv activated:

```bash
PYTHONPATH=src python -m seahealth.db.databricks_resources
```

Or directly:

```bash
/Users/alejandro/Desktop/seahealth/.venv/bin/python \
    -m seahealth.db.databricks_resources
```

The script reads `DATABRICKS_HOST` and `DATABRICKS_TOKEN` from `.env` at the
worktree root (the same file the existing `databricks_client.py` uses). The
token is passed only to the Databricks SDK; provisioning logs redact bearer
tokens from surfaced errors.

## What gets created

The most recent live provisioning run (2026-04-25) produced:

```
ensured: schema workspace.seahealth_bronze
ensured: schema workspace.seahealth_silver
ensured: schema workspace.seahealth_gold
ensured: volume workspace.seahealth_bronze.raw
ensured: csv /Volumes/workspace/seahealth_bronze/raw/vf_hackathon_india.csv  (10,391,754 bytes)
ensured: table workspace.seahealth_bronze.facilities_raw
ensured: table workspace.seahealth_bronze.chunks
ensured: table workspace.seahealth_silver.capabilities
ensured: table workspace.seahealth_silver.evidence_assessments
ensured: table workspace.seahealth_silver.contradictions
ensured: table workspace.seahealth_gold.facility_audits
ensured: table workspace.seahealth_gold.map_aggregates
ensured: workspace dir /Shared/seahealth
ensured: mlflow experiment /Shared/seahealth/extraction-runs  id=405251052688464
ensured: vs endpoint seahealth-vs
ensured: vs index workspace.seahealth_bronze.chunks_index
```

### Resources

| Layer  | Schema                          | Tables                                                           |
|--------|---------------------------------|------------------------------------------------------------------|
| Bronze | `workspace.seahealth_bronze`    | `facilities_raw`, `chunks`                                       |
| Silver | `workspace.seahealth_silver`    | `capabilities`, `evidence_assessments`, `contradictions`         |
| Gold   | `workspace.seahealth_gold`      | `facility_audits`, `map_aggregates`                              |

The bronze `chunks` table has Change Data Feed enabled so the Vector Search
delta-sync index picks up incremental updates.

### Volume

`workspace.seahealth_bronze.raw` — a managed UC volume mounted at
`/Volumes/workspace/seahealth_bronze/raw/`. Initial upload:
`vf_hackathon_india.csv` (the VF Hackathon India dataset, ~10MB).

### MLflow experiment

`/Shared/seahealth/extraction-runs` (workspace path). All Extractor agent runs
log traces here.

### Vector Search

- Endpoint: `seahealth-vs` (STANDARD).
- Index: `workspace.seahealth_bronze.chunks_index` (DELTA_SYNC,
  TRIGGERED, primary key `chunk_id`, synced columns `chunk_id`,
  `facility_id`, `source_type`, `text`, embedding source column `text`,
  embedding model `databricks-bge-large-en` — overridable via
  `SEAHEALTH_VS_EMBEDDING_ENDPOINT` env var).

## Cold-start expectations

First runs can spend most of their time waiting on Databricks control-plane
startup rather than local code:

- SQL warehouse start: `ensure_running()` waits up to 180 seconds by default.
- First SQL statement execution: `execute_sql()` requests synchronous waiting
  for up to 50 seconds, then polls the statement until a terminal state.
- Vector Search endpoint/index creation: best-effort and workspace dependent;
  if entitlement, model serving, or Vector Search is unavailable, provisioning
  returns `vector_search.status = unavailable` and the retriever falls back to
  local FAISS/BM25/TF mode.
- Local fallback retriever: FAISS plus sentence-transformers may cold-load a
  model on first use. If optional packages are absent, BM25 or dependency-free
  TF/cosine is used.

## Tear-down

There is no automated tear-down (deliberate — the workspace is shared).
Manual cleanup, in order, via SQL or the UI:

```sql
DROP TABLE IF EXISTS workspace.seahealth_bronze.facilities_raw;
DROP TABLE IF EXISTS workspace.seahealth_bronze.chunks;
DROP TABLE IF EXISTS workspace.seahealth_silver.capabilities;
DROP TABLE IF EXISTS workspace.seahealth_silver.evidence_assessments;
DROP TABLE IF EXISTS workspace.seahealth_silver.contradictions;
DROP TABLE IF EXISTS workspace.seahealth_gold.facility_audits;
DROP TABLE IF EXISTS workspace.seahealth_gold.map_aggregates;

DROP VOLUME IF EXISTS workspace.seahealth_bronze.raw;
DROP SCHEMA IF EXISTS workspace.seahealth_bronze CASCADE;
DROP SCHEMA IF EXISTS workspace.seahealth_silver CASCADE;
DROP SCHEMA IF EXISTS workspace.seahealth_gold   CASCADE;
```

Vector Search resources are removed via the API:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
w.vector_search_indexes.delete_index("workspace.seahealth_bronze.chunks_index")
w.vector_search_endpoints.delete_endpoint("seahealth-vs")
```

The MLflow experiment can be deleted from the workspace UI under
`/Shared/seahealth/extraction-runs`.

## Detecting Vector Search vs FAISS at runtime

Agents call `seahealth.db.retriever.get_retriever()`. The factory uses this
order:

1. If both `SEAHEALTH_VS_ENDPOINT` and `SEAHEALTH_VS_INDEX` env vars are set
   (or both kwargs are passed), instantiate a `VectorSearchRetriever`. This
   uses the `databricks-vectorsearch` SDK; if that import or the index lookup
   fails, the factory logs and falls back.
2. Otherwise, instantiate a `FaissRetriever` over `tables/chunks.parquet`.
   The `FaissRetriever` itself transparently picks the best backend at
   construction time:
     - `faiss` + `sentence-transformers` if both are installed
     - `rank_bm25` if installed
     - dependency-free TF/cosine over token bags (always works)

To force FAISS-mode locally, simply unset `SEAHEALTH_VS_*` env vars.

To force VS-mode against the live endpoint:

```bash
export SEAHEALTH_VS_ENDPOINT=seahealth-vs
export SEAHEALTH_VS_INDEX=workspace.seahealth_bronze.chunks_index
```

The `provision_all()` orchestrator returns `vector_search.status` of either
`ready`, `unavailable`, or `skipped`. Code that wants to gate on this can
inspect the dict; everything else just calls `get_retriever()` and trusts the
factory.

## Re-running the script

Every helper is idempotent:

- Schemas: `CREATE SCHEMA IF NOT EXISTS`.
- Volume: pre-checked with `volumes.read`; created only on `NotFound`.
- CSV: pre-checked with `files.get_metadata`; skipped if the remote object
  has the same byte size. If a previous run left a partial/stale remote file,
  the script deletes it before replacement and verifies the uploaded size when
  metadata is available.
- Tables: `CREATE TABLE IF NOT EXISTS` on every DDL.
- MLflow: `experiments.get_by_name` first, then `create_experiment` on
  `NotFound`.
- Vector Search: pre-checked with `get_endpoint` / `get_index`; created only
  on `NotFound`.

Catalog, schema, table, and Vector Search index identifiers are validated
against `[A-Za-z0-9_]+` before they are interpolated into SQL or SDK resource
names. Endpoint and model-serving endpoint names are not SQL identifiers and
may contain Databricks-supported hyphens.

A second run logs lines like `ensured: volume workspace.seahealth_bronze.raw
(already existed)` for every previously-created resource, with no API
mutation.

## Environment variables

| Variable                            | Purpose                                                                 |
|-------------------------------------|-------------------------------------------------------------------------|
| `DATABRICKS_HOST`                   | Workspace URL (loaded from `.env`).                                     |
| `DATABRICKS_TOKEN`                  | Personal access token (loaded from `.env`).                             |
| `DATABRICKS_WAREHOUSE_ID`           | Override which SQL warehouse to use.                                    |
| `SEAHEALTH_SKIP_VS`                 | Truthy → skip Vector Search provisioning.                               |
| `SEAHEALTH_VS_ENDPOINT`             | Force the retriever to use this endpoint.                               |
| `SEAHEALTH_VS_INDEX`                | Force the retriever to use this index.                                  |
| `SEAHEALTH_VS_EMBEDDING_ENDPOINT`   | Override the model endpoint (default `databricks-bge-large-en`).        |

## Tests

`tests/test_databricks_resources.py` — 10 mocked tests; never hits the wire.
`tests/test_retriever.py` — 6 offline tests over an in-memory DataFrame.
