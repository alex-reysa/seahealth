"""Pipeline: run the extractor agent over the demo subset.

Reads ``tables/chunks.parquet`` + ``tables/demo_subset.json``, calls the
extractor for each facility, and writes the resulting Capability rows to:

* ``tables/capabilities.parquet`` (always)
* Delta table ``seahealth.silver.capabilities`` if a Databricks SQL warehouse
  is reachable (best-effort; never blocks local runs).

MLflow tracing is wrapped behind ``MLFLOW_TRACKING_URI`` so unit tests don't
need a tracking server.

CLI: ``python -m seahealth.pipelines.extract --subset demo --limit 10``.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
from collections.abc import Iterable
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seahealth.agents.extractor import (
    DEFAULT_EXTRACTOR_MODEL,
    ExtractedCapabilities,
    extract_capabilities,
)
from seahealth.schemas import Capability

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TABLES_DIR = REPO_ROOT / "tables"
DEFAULT_SUBSET_PATH = DEFAULT_TABLES_DIR / "demo_subset.json"
DEFAULT_CHUNKS_PATH = DEFAULT_TABLES_DIR / "chunks.parquet"
DEFAULT_OUT_PATH = DEFAULT_TABLES_DIR / "capabilities.parquet"

DELTA_TABLE_FQN = "seahealth.silver.capabilities"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional integrations — both are best-effort.
# ---------------------------------------------------------------------------


def _maybe_get_sql_executor():
    """Return ``execute_sql`` from F-1's module if importable, else ``None``."""
    try:
        module = importlib.import_module("seahealth.db.sql_warehouse")
    except Exception:
        return None
    return getattr(module, "execute_sql", None)


@contextmanager
def _maybe_mlflow_span(name: str, attributes: dict[str, Any] | None = None):
    """Open an MLflow span only if MLFLOW_TRACKING_URI is configured."""
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        yield None
        return
    try:
        import mlflow  # type: ignore

        with mlflow.start_span(name=name, attributes=attributes or {}) as span:
            yield span
    except Exception as exc:  # pragma: no cover — trace plumbing must never crash
        logger.warning("mlflow span %s failed: %s", name, exc)
        yield None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def _load_subset(subset_path: Path, subset: str) -> list[str]:
    if not subset_path.exists():
        raise FileNotFoundError(f"subset file not found: {subset_path}")
    payload = json.loads(subset_path.read_text(encoding="utf-8"))
    if subset == "demo":
        ids = payload.get("facility_ids") or []
    else:
        ids = payload.get(subset) or []
    return [str(i) for i in ids]


def _load_chunks(chunks_path: Path) -> pd.DataFrame:
    if not chunks_path.exists():
        raise FileNotFoundError(f"chunks parquet not found: {chunks_path}")
    return pq.read_table(chunks_path).to_pandas()


def _chunks_for_facility(df: pd.DataFrame, facility_id: str) -> list[dict]:
    return df[df["facility_id"] == facility_id].to_dict(orient="records")


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def _capability_to_row(cap: Capability) -> dict[str, Any]:
    payload = cap.model_dump(mode="json")
    return {
        "facility_id": payload["facility_id"],
        "capability_type": payload["capability_type"],
        "claimed": payload["claimed"],
        "source_doc_id": payload["source_doc_id"],
        "extractor_model": payload["extractor_model"],
        "extracted_at": payload["extracted_at"],
        "evidence_refs_json": json.dumps(payload["evidence_refs"], ensure_ascii=False),
    }


def _write_parquet(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        # Empty parquet — still write an empty file with the canonical schema
        # so downstream readers don't blow up.
        empty = pd.DataFrame(
            columns=[
                "facility_id",
                "capability_type",
                "claimed",
                "source_doc_id",
                "extractor_model",
                "extracted_at",
                "evidence_refs_json",
            ]
        )
        table = pa.Table.from_pandas(empty, preserve_index=False)
        tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
        pq.write_table(table, tmp_path)
        tmp_path.replace(out_path)
        return
    df = pd.DataFrame(rows)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp_path)
    tmp_path.replace(out_path)


def _maybe_write_delta(rows: list[dict[str, Any]]) -> bool:
    """Best-effort mirror to ``seahealth.silver.capabilities``.

    Returns True if a Delta write was attempted; False if skipped.
    """
    if not rows:
        return False
    if not os.environ.get("DATABRICKS_HOST"):
        return False
    execute_sql = _maybe_get_sql_executor()
    if execute_sql is None:
        logger.info("seahealth.db.sql_warehouse not importable; skipping Delta write")
        return False
    try:
        for row in rows:
            execute_sql(
                f"INSERT INTO {DELTA_TABLE_FQN} "
                "(facility_id, capability_type, claimed, source_doc_id, "
                "extractor_model, extracted_at, evidence_refs_json) "
                "VALUES (:facility_id, :capability_type, :claimed, :source_doc_id, "
                ":extractor_model, :extracted_at, :evidence_refs_json)",
                params=row,
            )
        return True
    except Exception as exc:  # pragma: no cover — SQL plumbing failures are non-fatal
        logger.warning("delta write skipped: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def main(
    subset: str = "demo",
    limit: int | None = None,
    *,
    tables_dir: str | Path | None = None,
    subset_path: str | Path | None = None,
    chunks_path: str | Path | None = None,
    out_path: str | Path | None = None,
    extract_fn=extract_capabilities,
    model: str = DEFAULT_EXTRACTOR_MODEL,
) -> dict[str, Any]:
    """Run the extractor pipeline.

    Args:
        subset: Key into the subset JSON (``demo`` reads ``facility_ids``).
        limit: Cap the number of facilities processed.
        tables_dir: Override the tables directory; ``subset_path`` /
            ``chunks_path`` / ``out_path`` default underneath it.
        extract_fn: Override the extractor (handy for tests).
        model: Anthropic model id forwarded to the extractor.

    Returns:
        Summary dict with counts and output paths.
    """
    tables = Path(tables_dir) if tables_dir is not None else DEFAULT_TABLES_DIR
    subset_p = Path(subset_path) if subset_path is not None else tables / "demo_subset.json"
    chunks_p = Path(chunks_path) if chunks_path is not None else tables / "chunks.parquet"
    out_p = Path(out_path) if out_path is not None else tables / "capabilities.parquet"

    facility_ids = _load_subset(subset_p, subset)
    if limit is not None:
        facility_ids = facility_ids[:limit]
    chunks_df = _load_chunks(chunks_p)

    all_rows: list[dict[str, Any]] = []
    facility_count = 0
    capability_count = 0
    skipped_zero_chunk_count = 0
    failed_count = 0
    total = len(facility_ids)
    for idx, facility_id in enumerate(facility_ids, start=1):
        chunks = _chunks_for_facility(chunks_df, facility_id)
        if not chunks:
            skipped_zero_chunk_count += 1
            print(f"[extract {idx}/{total}] skip {facility_id} (no chunks)", flush=True)
            logger.warning("skipping %s: no chunks found", facility_id)
            continue
        with _maybe_mlflow_span(
            "extract_capabilities",
            attributes={"facility_id": facility_id, "chunk_count": len(chunks)},
        ):
            try:
                extracted: ExtractedCapabilities = extract_fn(
                    facility_id, chunks, model=model
                )
            except Exception as exc:  # pragma: no cover — agent failure must not halt
                failed_count += 1
                print(
                    f"[extract {idx}/{total}] FAIL {facility_id}: {str(exc)[:120]}",
                    flush=True,
                )
                logger.warning("extract failed for %s: %s", facility_id, exc)
                continue
        facility_count += 1
        new_caps = 0
        for cap in extracted.capabilities:
            all_rows.append(_capability_to_row(cap))
            capability_count += 1
            new_caps += 1
        print(
            f"[extract {idx}/{total}] {facility_id} caps={new_caps}",
            flush=True,
        )

    _write_parquet(all_rows, out_p)
    delta_written = _maybe_write_delta(all_rows)

    summary = {
        "subset": subset,
        "facility_count": facility_count,
        "capability_count": capability_count,
        "skipped_zero_chunk_count": skipped_zero_chunk_count,
        "out_path": str(out_p),
        "delta_written": delta_written,
    }
    print(
        f"[extract] facilities={facility_count} capabilities={capability_count} "
        f"parquet={out_p} delta={delta_written}"
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the SeaHealth extractor agent over a subset.")
    p.add_argument("--subset", type=str, default="demo")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--tables-dir", type=str, default=None)
    p.add_argument("--model", type=str, default=DEFAULT_EXTRACTOR_MODEL)
    return p


def _cli(argv: Iterable[str] | None = None) -> None:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    main(
        subset=args.subset,
        limit=args.limit,
        tables_dir=args.tables_dir,
        model=args.model,
    )


if __name__ == "__main__":  # pragma: no cover
    _cli()


# ``nullcontext`` retained as a safety import for callers that monkeypatch
# ``_maybe_mlflow_span`` with a no-op factory.
__all__ = ["main", "ExtractedCapabilities", "nullcontext"]
