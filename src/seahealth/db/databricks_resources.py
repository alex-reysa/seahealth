"""Idempotent provisioning for the SeaHealth Databricks workspace.

The :func:`provision_all` entrypoint creates everything the agents need to run
end-to-end:

  1. Detects a writeable Unity Catalog (or falls back to ``hive_metastore``).
  2. Ensures the bronze/silver/gold schemas.
  3. Ensures a managed UC volume for raw uploads.
  4. Uploads the VF Hackathon CSV (skipping if already present + same size).
  5. Creates 7 Delta tables (DDL only, no data movement) via the SQL warehouse.
  6. Ensures the MLflow extraction-runs experiment.
  7. Best-effort attempts to provision Vector Search; reports ``unavailable``
     when the workspace doesn't have it enabled, so the retriever can fall
     back to FAISS.

Each helper is safe to re-run. They all log a single line per resource to
stdout so the provisioning run is auditable.

Run as a module to provision everything::

    python -m seahealth.db.databricks_resources
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any

from databricks.sdk.errors import NotFound
from databricks.sdk.service.catalog import VolumeType

from .databricks_client import get_workspace
from .sql_warehouse import ensure_running, execute_sql, get_warehouse_id

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

BRONZE_SCHEMA = "seahealth_bronze"
SILVER_SCHEMA = "seahealth_silver"
GOLD_SCHEMA = "seahealth_gold"

VOLUME_NAME = "raw"

DBFS_FALLBACK = "/FileStore/seahealth/raw"

DEFAULT_CSV_PATH = (
    "/Users/alejandro/Desktop/seahealth/"
    "VF_Hackathon_Dataset_India_Large.xlsx - VF_Hackathon_Dataset_India_Larg.csv"
)

VS_ENDPOINT_NAME = "seahealth-vs"
VS_INDEX_SUFFIX = "chunks_index"

MLFLOW_EXPERIMENT_PATH = "/Shared/seahealth/extraction-runs"


def _log(msg: str) -> None:
    """Write one line to stdout AND to the module logger."""
    print(msg, flush=True)
    logger.info(msg)


# --------------------------------------------------------------------------- #
# Catalog / schema / volume
# --------------------------------------------------------------------------- #

def detect_catalog() -> str:
    """Return the first writeable catalog, falling back to ``hive_metastore``.

    Order of preference: ``main`` → ``workspace`` → any non-system catalog the
    PAT can list. If Unity Catalog is disabled (no listable catalogs at all),
    we return the literal string ``"hive_metastore"`` so the caller can still
    create tables.
    """
    w = get_workspace()
    try:
        catalogs = list(w.catalogs.list())
    except Exception as exc:  # pragma: no cover - workspace without UC
        _log(f"detect_catalog: catalogs.list failed ({exc!r}); using hive_metastore")
        return "hive_metastore"

    names = {c.name: c for c in catalogs}
    for preferred in ("main", "workspace"):
        if preferred in names:
            _log(f"detect_catalog: using preferred catalog {preferred!r}")
            return preferred

    # Any non-system catalog.
    for c in catalogs:
        ctype = c.catalog_type.value if c.catalog_type is not None else ""
        if "SYSTEM" not in ctype:
            _log(f"detect_catalog: using catalog {c.name!r} (type={ctype})")
            return c.name

    _log("detect_catalog: no writeable UC catalog found; falling back to hive_metastore")
    return "hive_metastore"


def ensure_schemas(catalog: str) -> dict[str, str]:
    """Create or fetch the bronze/silver/gold schemas under ``catalog``.

    Uses ``CREATE SCHEMA IF NOT EXISTS`` via the SQL warehouse so the same
    code path works for UC and the legacy ``hive_metastore`` catalog.

    Returns:
        Mapping of layer → fully-qualified schema name (``catalog.schema``).
    """
    ensure_running()
    out: dict[str, str] = {}
    for layer, schema in (
        ("bronze", BRONZE_SCHEMA),
        ("silver", SILVER_SCHEMA),
        ("gold", GOLD_SCHEMA),
    ):
        full = f"{catalog}.{schema}"
        try:
            execute_sql(f"CREATE SCHEMA IF NOT EXISTS {full}")
            _log(f"ensured: schema {full}")
        except Exception as exc:
            # Some workspaces disallow IF NOT EXISTS for hive_metastore — try plain CREATE.
            msg = str(exc)
            if "already exists" in msg.lower():
                _log(f"ensured: schema {full} (already existed)")
            else:
                raise
        out[layer] = full
    return out


def ensure_volume(catalog: str) -> str:
    """Ensure a managed UC volume at ``catalog.<bronze>.raw`` and return its path.

    UC managed volumes are addressable as ``/Volumes/<catalog>/<schema>/<name>``
    on the cluster filesystem. When UC is not available (catalog is
    ``hive_metastore``), we return the DBFS fallback path :data:`DBFS_FALLBACK`.
    """
    if catalog == "hive_metastore":
        _log(f"ensure_volume: UC unavailable, using DBFS path {DBFS_FALLBACK}")
        return DBFS_FALLBACK

    w = get_workspace()
    full = f"{catalog}.{BRONZE_SCHEMA}.{VOLUME_NAME}"
    try:
        w.volumes.read(full)
        _log(f"ensured: volume {full} (already existed)")
    except NotFound:
        w.volumes.create(
            catalog_name=catalog,
            schema_name=BRONZE_SCHEMA,
            name=VOLUME_NAME,
            volume_type=VolumeType.MANAGED,
            comment="SeaHealth raw uploads (CSV, raw docs)",
        )
        _log(f"ensured: volume {full} (created)")
    except Exception as exc:
        # Fallback for SDKs that surface generic API errors instead of NotFound.
        if "does not exist" in str(exc).lower() or "not_found" in str(exc).lower():
            w.volumes.create(
                catalog_name=catalog,
                schema_name=BRONZE_SCHEMA,
                name=VOLUME_NAME,
                volume_type=VolumeType.MANAGED,
                comment="SeaHealth raw uploads (CSV, raw docs)",
            )
            _log(f"ensured: volume {full} (created)")
        else:
            raise
    return f"/Volumes/{catalog}/{BRONZE_SCHEMA}/{VOLUME_NAME}"


def upload_csv_to_volume(volume_path: str, local_csv_path: str = DEFAULT_CSV_PATH) -> str:
    """Upload the VF Hackathon CSV to ``volume_path`` and return the remote path.

    Skips re-upload if the remote object exists with the same size as the local
    file. ``volume_path`` may be either a UC volume root
    (``/Volumes/<cat>/<schema>/<name>``) or the DBFS fallback root.
    """
    src = Path(local_csv_path)
    if not src.exists():
        raise FileNotFoundError(f"CSV not found at {src}")

    w = get_workspace()
    remote_path = f"{volume_path.rstrip('/')}/vf_hackathon_india.csv"
    local_size = src.stat().st_size

    # Idempotency: skip if a same-size object is already present.
    try:
        meta = w.files.get_metadata(remote_path)
        remote_size = getattr(meta, "content_length", None)
        if remote_size is not None and int(remote_size) == local_size:
            _log(f"ensured: csv {remote_path} (already present, {local_size} bytes)")
            return remote_path
    except NotFound:
        pass
    except Exception:
        # Bucket: any other read error → just re-upload.
        pass

    with src.open("rb") as fh:
        # `files.upload` works for both /Volumes paths and DBFS-style paths.
        w.files.upload(file_path=remote_path, contents=fh, overwrite=True)
    _log(f"ensured: csv {remote_path} (uploaded {local_size} bytes)")
    return remote_path


# --------------------------------------------------------------------------- #
# Delta tables
# --------------------------------------------------------------------------- #

def _facilities_raw_columns() -> str:
    """Mirror of the VF CSV header — STRING for everything plus provenance.

    We deliberately use STRING types in bronze: schema enforcement happens in
    the silver/gold layer.
    """
    csv_cols = [
        "name", "phone_numbers", "officialPhone", "email", "websites",
        "officialWebsite", "yearEstablished", "facebookLink", "twitterLink",
        "linkedinLink", "instagramLink", "address_line1", "address_line2",
        "address_line3", "address_city", "address_stateOrRegion",
        "address_zipOrPostcode", "address_country", "address_countryCode",
        "facilityTypeId", "operatorTypeId", "affiliatedHospitals",
        "specialties", "workingHours", "numberOfDoctors", "capacityBeds",
        "fees", "averageRating", "ratingCount", "reviews",
        "googleMapsLink", "latitude", "longitude",
    ]
    body = ",\n  ".join(f"`{c}` STRING" for c in csv_cols)
    body += ",\n  `_source_uri` STRING,\n  `_ingested_at` TIMESTAMP"
    return body


_DDL_TEMPLATES: dict[str, str] = {
    # ---- bronze --------------------------------------------------------- #
    "facilities_raw": """
        CREATE TABLE IF NOT EXISTS {bronze}.facilities_raw (
          {facilities_columns}
        ) USING DELTA
    """,
    "chunks": """
        CREATE TABLE IF NOT EXISTS {bronze}.chunks (
          chunk_id STRING,
          facility_id STRING,
          source_type STRING,
          text STRING,
          span_start INT,
          span_end INT,
          source_doc_id STRING,
          indexed_at TIMESTAMP
        ) USING DELTA
        TBLPROPERTIES (delta.enableChangeDataFeed = true)
    """,
    # ---- silver --------------------------------------------------------- #
    "capabilities": """
        CREATE TABLE IF NOT EXISTS {silver}.capabilities (
          facility_id STRING,
          capability_type STRING,
          claimed BOOLEAN,
          evidence_refs ARRAY<STRUCT<
            source_doc_id: STRING,
            facility_id: STRING,
            chunk_id: STRING,
            row_id: STRING,
            span_start: INT,
            span_end: INT,
            snippet: STRING,
            source_type: STRING,
            source_observed_at: TIMESTAMP,
            retrieved_at: TIMESTAMP
          >>,
          source_doc_id STRING,
          extracted_at TIMESTAMP,
          extractor_model STRING,
          mlflow_trace_id STRING
        ) USING DELTA
    """,
    "evidence_assessments": """
        CREATE TABLE IF NOT EXISTS {silver}.evidence_assessments (
          evidence_ref_id STRING,
          capability_type STRING,
          facility_id STRING,
          stance STRING,
          reasoning STRING,
          assessed_at TIMESTAMP
        ) USING DELTA
    """,
    "contradictions": """
        CREATE TABLE IF NOT EXISTS {silver}.contradictions (
          contradiction_type STRING,
          capability_type STRING,
          facility_id STRING,
          evidence_for ARRAY<STRUCT<
            source_doc_id: STRING,
            facility_id: STRING,
            chunk_id: STRING,
            row_id: STRING,
            span_start: INT,
            span_end: INT,
            snippet: STRING,
            source_type: STRING,
            source_observed_at: TIMESTAMP,
            retrieved_at: TIMESTAMP
          >>,
          evidence_against ARRAY<STRUCT<
            source_doc_id: STRING,
            facility_id: STRING,
            chunk_id: STRING,
            row_id: STRING,
            span_start: INT,
            span_end: INT,
            snippet: STRING,
            source_type: STRING,
            source_observed_at: TIMESTAMP,
            retrieved_at: TIMESTAMP
          >>,
          severity STRING,
          reasoning STRING,
          detected_by STRING,
          detected_at TIMESTAMP
        ) USING DELTA
    """,
    # ---- gold ----------------------------------------------------------- #
    "facility_audits": """
        CREATE TABLE IF NOT EXISTS {gold}.facility_audits (
          facility_id STRING,
          name STRING,
          location STRUCT<lat: DOUBLE, lng: DOUBLE, pin_code: STRING>,
          capabilities ARRAY<STRUCT<
            facility_id: STRING,
            capability_type: STRING,
            claimed: BOOLEAN,
            source_doc_id: STRING,
            extracted_at: TIMESTAMP,
            extractor_model: STRING
          >>,
          trust_scores MAP<STRING, STRUCT<
            score: DOUBLE,
            band: STRING,
            contradictions: INT,
            verifying_evidence: INT
          >>,
          total_contradictions INT,
          last_audited_at TIMESTAMP,
          mlflow_trace_id STRING
        ) USING DELTA
    """,
    "map_aggregates": """
        CREATE TABLE IF NOT EXISTS {gold}.map_aggregates (
          region_id STRING,
          region_name STRING,
          state STRING,
          capability_type STRING,
          population INT,
          verified_facilities_count INT,
          flagged_facilities_count INT,
          gap_population INT,
          centroid STRUCT<lat: DOUBLE, lng: DOUBLE, pin_code: STRING>
        ) USING DELTA
    """,
}


def ensure_delta_tables(bronze: str, silver: str, gold: str) -> list[str]:
    """Create the 7 Delta tables (DDL only) under the given fully-qualified schemas.

    Args:
        bronze: ``catalog.seahealth_bronze``.
        silver: ``catalog.seahealth_silver``.
        gold:   ``catalog.seahealth_gold``.

    Returns:
        Fully-qualified table names in creation order.
    """
    ensure_running()
    facilities_columns = _facilities_raw_columns()

    full_names = [
        f"{bronze}.facilities_raw",
        f"{bronze}.chunks",
        f"{silver}.capabilities",
        f"{silver}.evidence_assessments",
        f"{silver}.contradictions",
        f"{gold}.facility_audits",
        f"{gold}.map_aggregates",
    ]

    template_keys = [
        "facilities_raw",
        "chunks",
        "capabilities",
        "evidence_assessments",
        "contradictions",
        "facility_audits",
        "map_aggregates",
    ]

    for fq, key in zip(full_names, template_keys, strict=True):
        ddl = _DDL_TEMPLATES[key].format(
            bronze=bronze,
            silver=silver,
            gold=gold,
            facilities_columns=facilities_columns,
        ).strip()
        try:
            execute_sql(ddl)
            _log(f"ensured: table {fq}")
        except Exception as exc:
            if "already exists" in str(exc).lower():
                _log(f"ensured: table {fq} (already existed)")
            else:
                raise

    return full_names


# --------------------------------------------------------------------------- #
# MLflow + Vector Search
# --------------------------------------------------------------------------- #

def _ensure_workspace_directory(path: str) -> None:
    """Create a workspace folder (idempotent) so MLflow experiments can live there."""
    w = get_workspace()
    try:
        from databricks.sdk.service.workspace import ObjectType  # type: ignore

        try:
            obj = w.workspace.get_status(path)
            if obj.object_type == ObjectType.DIRECTORY:
                return
        except NotFound:
            pass
        except Exception:
            pass

        w.workspace.mkdirs(path)
        _log(f"ensured: workspace dir {path}")
    except Exception as exc:
        # Best-effort — some workspaces may not allow programmatic mkdirs;
        # the experiment-create call below will surface any real issue.
        _log(f"_ensure_workspace_directory: {path} → {exc!r}")


def ensure_mlflow_experiment(path: str = MLFLOW_EXPERIMENT_PATH) -> str:
    """Create or fetch an MLflow experiment at the given workspace path.

    Returns:
        ``experiment_id`` (string).
    """
    w = get_workspace()
    try:
        existing = w.experiments.get_by_name(path)
        exp_id = existing.experiment.experiment_id if existing.experiment else None
        if exp_id:
            _log(f"ensured: mlflow experiment {path} id={exp_id}")
            return exp_id
    except NotFound:
        pass
    except Exception as exc:
        # Some SDK versions throw a generic error when not found.
        if "does not exist" not in str(exc).lower() and "not_found" not in str(exc).lower():
            raise

    # Ensure parent directory exists (e.g. /Shared/seahealth for /Shared/seahealth/extraction-runs).
    parent = path.rsplit("/", 1)[0]
    if parent:
        _ensure_workspace_directory(parent)

    created = w.experiments.create_experiment(name=path)
    exp_id = created.experiment_id
    _log(f"ensured: mlflow experiment {path} id={exp_id}")
    return exp_id


def ensure_vector_search(bronze: str | None = None) -> dict[str, str]:
    """Best-effort Vector Search provisioning.

    On any failure (workspace doesn't have VS, missing entitlement, etc.) we
    return ``{"status": "unavailable", "fallback": "faiss"}`` and let
    :mod:`seahealth.db.retriever` fall back. On success we return the live
    endpoint + index names.

    Args:
        bronze: fully-qualified bronze schema (e.g. ``workspace.seahealth_bronze``).
            When omitted we don't even attempt to create the index, only the
            endpoint, since the index requires a source table.
    """
    w = get_workspace()
    try:
        from databricks.sdk.service.vectorsearch import (
            DeltaSyncVectorIndexSpecRequest,
            EmbeddingSourceColumn,
            EndpointType,
            PipelineType,
            VectorIndexType,
        )
    except Exception as exc:
        _log(f"vector_search: SDK module unavailable ({exc!r}); fallback=faiss")
        return {"status": "unavailable", "fallback": "faiss"}

    # 1. Endpoint.
    try:
        try:
            ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT_NAME)
            _log(f"ensured: vs endpoint {VS_ENDPOINT_NAME} (already existed)")
        except Exception:
            ep = None
        if ep is None:
            w.vector_search_endpoints.create_endpoint(
                name=VS_ENDPOINT_NAME,
                endpoint_type=EndpointType.STANDARD,
            )
            _log(f"ensured: vs endpoint {VS_ENDPOINT_NAME} (created)")
    except Exception as exc:
        _log(f"vector_search: endpoint provisioning failed ({exc!r}); fallback=faiss")
        return {"status": "unavailable", "fallback": "faiss", "error": str(exc)[:200]}

    # 2. Index — requires bronze.chunks to exist.
    if bronze is None:
        return {
            "status": "ready",
            "endpoint": VS_ENDPOINT_NAME,
            "index": "",
            "note": "endpoint only; pass bronze= to create the index",
        }

    index_name = f"{bronze}.{VS_INDEX_SUFFIX}"
    try:
        try:
            w.vector_search_indexes.get_index(index_name)
            _log(f"ensured: vs index {index_name} (already existed)")
        except Exception:
            w.vector_search_indexes.create_index(
                name=index_name,
                endpoint_name=VS_ENDPOINT_NAME,
                primary_key="chunk_id",
                index_type=VectorIndexType.DELTA_SYNC,
                delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                    source_table=f"{bronze}.chunks",
                    pipeline_type=PipelineType.TRIGGERED,
                    embedding_source_columns=[
                        EmbeddingSourceColumn(
                            name="text",
                            embedding_model_endpoint_name=os.getenv(
                                "SEAHEALTH_VS_EMBEDDING_ENDPOINT",
                                "databricks-bge-large-en",
                            ),
                        )
                    ],
                ),
            )
            _log(f"ensured: vs index {index_name} (created)")
    except Exception as exc:
        _log(f"vector_search: index provisioning failed ({exc!r}); fallback=faiss")
        return {
            "status": "unavailable",
            "fallback": "faiss",
            "endpoint": VS_ENDPOINT_NAME,
            "error": str(exc)[:200],
        }

    return {"status": "ready", "endpoint": VS_ENDPOINT_NAME, "index": index_name}


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #

def provision_all(
    csv_path: str = DEFAULT_CSV_PATH,
    skip_vector_search: bool | None = None,
) -> dict[str, Any]:
    """Run the full provisioning pipeline. Idempotent.

    Args:
        csv_path: source CSV to upload to the bronze volume.
        skip_vector_search: when True, skip VS provisioning entirely. When
            unset, honors the ``SEAHEALTH_SKIP_VS`` env var (any truthy value
            skips). Default behavior is to attempt VS.
    """
    if skip_vector_search is None:
        skip_vector_search = os.getenv("SEAHEALTH_SKIP_VS", "").lower() in {
            "1", "true", "yes", "on",
        }

    out: dict[str, Any] = {}

    catalog = detect_catalog()
    out["catalog"] = catalog

    # Ensure warehouse is running once up-front so subsequent SQL is fast.
    out["warehouse_id"] = ensure_running(get_warehouse_id())

    schemas = ensure_schemas(catalog)
    out["schemas"] = schemas

    volume_path = ensure_volume(catalog)
    out["volume_path"] = volume_path

    csv_remote = upload_csv_to_volume(volume_path, csv_path)
    out["csv_remote"] = csv_remote

    tables = ensure_delta_tables(schemas["bronze"], schemas["silver"], schemas["gold"])
    out["tables"] = tables

    out["mlflow_experiment_id"] = ensure_mlflow_experiment()

    if skip_vector_search:
        _log("vector_search: skipped (SEAHEALTH_SKIP_VS set)")
        out["vector_search"] = {"status": "skipped", "fallback": "faiss"}
    else:
        out["vector_search"] = ensure_vector_search(bronze=schemas["bronze"])

    _log("provision_all: done")
    return out


def main() -> None:  # pragma: no cover - manual entrypoint
    """Module entrypoint: ``python -m seahealth.db.databricks_resources``."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    result = provision_all()
    _log(f"\nFINAL: {result}")


if __name__ == "__main__":  # pragma: no cover
    main()


# Re-exported for callers that just want a constant.
__all__ = [
    "BRONZE_SCHEMA",
    "DBFS_FALLBACK",
    "DEFAULT_CSV_PATH",
    "GOLD_SCHEMA",
    "MLFLOW_EXPERIMENT_PATH",
    "SILVER_SCHEMA",
    "VOLUME_NAME",
    "VS_ENDPOINT_NAME",
    "detect_catalog",
    "ensure_delta_tables",
    "ensure_mlflow_experiment",
    "ensure_schemas",
    "ensure_vector_search",
    "ensure_volume",
    "provision_all",
    "upload_csv_to_volume",
]


# Suppress unused import warnings for io module preserved for future use.
_ = io
