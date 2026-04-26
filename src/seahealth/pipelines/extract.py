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
import threading
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _synthesize_local_trace_id(facility_id: str, run_uuid: str) -> str:
    """Build the deterministic local trace id stamped on Capabilities.

    Format: ``local::<facility_id>::<run_uuid>``. The ``run_uuid`` is shared
    across every facility processed in a single ``main()`` invocation so the
    UI can group capabilities by extraction run; the per-facility tail keeps
    each Capability's trace id unique.
    """
    return f"local::{facility_id}::{run_uuid}"


def _extract_real_trace_id(span: Any) -> str | None:
    """Best-effort pull of the real MLflow trace id from a live span."""
    if span is None:
        return None
    for attr in ("trace_id", "request_id"):
        candidate = getattr(span, attr, None)
        if candidate:
            return str(candidate)
    return None


@contextmanager
def _maybe_mlflow_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    *,
    facility_id: str | None = None,
    run_uuid: str | None = None,
):
    """Open an MLflow span when configured; always yield a trace_id string.

    The yielded value is the trace id string a downstream UI can use to link a
    Capability back to one extraction run:

    * If ``MLFLOW_TRACKING_URI`` is set and ``mlflow`` imports cleanly, prefer
      the real span's ``trace_id`` (or ``request_id`` on older MLflow).
    * Otherwise (or if mlflow is unavailable), synthesize
      ``local::<facility_id>::<run_uuid>``. Both arguments must be passed when
      the caller wants a deterministic synthetic id; if either is missing we
      yield ``None``.
    """
    fallback = (
        _synthesize_local_trace_id(facility_id, run_uuid)
        if facility_id and run_uuid
        else None
    )
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        yield fallback
        return
    try:
        import mlflow  # type: ignore

        with mlflow.start_span(name=name, attributes=attributes or {}) as span:
            real = _extract_real_trace_id(span)
            yield real or fallback
    except Exception as exc:  # pragma: no cover — trace plumbing must never crash
        logger.warning("mlflow span %s failed: %s", name, exc)
        yield fallback


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


def _call_extract_fn(
    fn: Any,
    facility_id: str,
    chunks: list[dict[str, Any]],
    *,
    model: str,
    mlflow_trace_id: str | None,
) -> ExtractedCapabilities:
    """Invoke ``extract_fn`` with ``mlflow_trace_id`` if its signature accepts it.

    Test fakes that haven't been updated to the new keyword still work — we
    fall back to calling without the kwarg.
    """
    import inspect

    try:
        sig = inspect.signature(fn)
        params = sig.parameters
        accepts = "mlflow_trace_id" in params or any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
    except (TypeError, ValueError):
        accepts = False

    if accepts:
        return fn(facility_id, chunks, model=model, mlflow_trace_id=mlflow_trace_id)
    return fn(facility_id, chunks, model=model)


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
        "mlflow_trace_id": payload.get("mlflow_trace_id"),
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
                "mlflow_trace_id",
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
                "extractor_model, extracted_at, evidence_refs_json, "
                "mlflow_trace_id) "
                "VALUES (:facility_id, :capability_type, :claimed, :source_doc_id, "
                ":extractor_model, :extracted_at, :evidence_refs_json, "
                ":mlflow_trace_id)",
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
    start_index: int = 0,
    flush_every: int = 50,
    resume: bool = False,
    workers: int = 1,
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
        start_index: Start at ``facility_ids[start_index:]`` — for batch /
            resume runs over the 10k.
        flush_every: Write the partial parquet every ``flush_every`` facilities
            so a crash mid-run doesn't lose progress. Default 50.
        resume: If True and the output parquet already exists, load already-
            extracted facility_ids and skip them. Lets a crashed 10k run
            pick up where it left off.
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
    if start_index:
        facility_ids = facility_ids[start_index:]
    if limit is not None:
        facility_ids = facility_ids[:limit]
    chunks_df = _load_chunks(chunks_p)

    # Resume support: pre-load already-extracted facility_ids and skip them.
    all_rows: list[dict[str, Any]] = []
    already_done: set[str] = set()
    if resume and out_p.exists():
        try:
            existing = pd.read_parquet(out_p)
            all_rows = existing.to_dict(orient="records")
            already_done = set(existing["facility_id"].astype(str).unique())
            print(
                f"[extract] resume: loaded {len(all_rows)} existing rows "
                f"covering {len(already_done)} facilities",
                flush=True,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("resume failed (will overwrite): %s", exc)

    # One run_uuid per main() invocation. Every facility processed in this run
    # shares this uuid so a downstream UI can group capabilities under a single
    # extraction run; per-Capability uniqueness still comes from the
    # ``facility_id`` portion of the synthesized trace id.
    run_uuid = uuid.uuid4().hex

    facility_count = 0
    capability_count = 0
    skipped_zero_chunk_count = 0
    failed_count = 0
    skipped_done_count = 0
    total = len(facility_ids)

    # Build the pending-work list once. Skip facilities already in the resume set
    # AND facilities with zero chunks (handle them inline so they're counted).
    pending: list[tuple[int, str, list[dict[str, Any]]]] = []
    for idx, fid in enumerate(facility_ids, start=1):
        if fid in already_done:
            skipped_done_count += 1
            continue
        chunks = _chunks_for_facility(chunks_df, fid)
        if not chunks:
            skipped_zero_chunk_count += 1
            print(f"[extract {idx}/{total}] skip {fid} (no chunks)", flush=True)
            logger.warning("skipping %s: no chunks found", fid)
            continue
        pending.append((idx, fid, chunks))

    workers = max(1, int(workers))
    state_lock = threading.Lock()
    completed_total = len(already_done) + skipped_zero_chunk_count + skipped_done_count

    def _do_one(item: tuple[int, str, list[dict[str, Any]]]):
        idx, fid, chunks = item
        with _maybe_mlflow_span(
            "extract_capabilities",
            attributes={"facility_id": fid, "chunk_count": len(chunks)},
            facility_id=fid,
            run_uuid=run_uuid,
        ) as trace_id:
            try:
                extracted: ExtractedCapabilities = _call_extract_fn(
                    extract_fn, fid, chunks, model=model, mlflow_trace_id=trace_id
                )
                return ("ok", idx, fid, [_capability_to_row(c) for c in extracted.capabilities])
            except Exception as exc:  # pragma: no cover
                return ("fail", idx, fid, str(exc))

    def _on_result(kind: str, idx: int, fid: str, payload: Any) -> None:
        nonlocal facility_count, capability_count, failed_count, completed_total
        with state_lock:
            completed_total += 1
            if kind == "ok":
                facility_count += 1
                rows = payload  # list[dict]
                all_rows.extend(rows)
                capability_count += len(rows)
                already_done.add(fid)
                print(f"[extract {completed_total}/{total}] {fid} caps={len(rows)}", flush=True)
            else:
                failed_count += 1
                print(
                    f"[extract {completed_total}/{total}] FAIL {fid}: {str(payload)[:120]}",
                    flush=True,
                )
                logger.warning("extract failed for %s: %s", fid, payload)
            if flush_every and (completed_total % flush_every == 0):
                _write_parquet(all_rows, out_p)
                print(
                    f"[extract {completed_total}/{total}] flushed {len(all_rows)} rows -> {out_p}",
                    flush=True,
                )

    if workers == 1:
        # Sequential path — preserves the original ordering and behavior.
        for item in pending:
            kind, idx, fid, payload = _do_one(item)
            _on_result(kind, idx, fid, payload)
    else:
        # Parallel path — N concurrent in-flight LLM calls. The OpenAI SDK
        # client is thread-safe (httpx connection pool); _on_result holds a
        # lock around shared mutable state so flush + counters stay coherent.
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_do_one, item) for item in pending]
            for fut in as_completed(futures):
                kind, idx, fid, payload = fut.result()
                _on_result(kind, idx, fid, payload)

    _write_parquet(all_rows, out_p)
    delta_written = _maybe_write_delta(all_rows)

    summary = {
        "subset": subset,
        "facility_count": facility_count,
        "capability_count": capability_count,
        "skipped_zero_chunk_count": skipped_zero_chunk_count,
        "skipped_already_done_count": skipped_done_count,
        "failed_count": failed_count,
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
    p.add_argument("--start-index", type=int, default=0,
                   help="Start at facility_ids[start_index:] for batch / resume runs.")
    p.add_argument("--flush-every", type=int, default=50,
                   help="Write the partial parquet every N facilities so a crash mid-run doesn't lose progress (default: 50).")
    p.add_argument("--resume", action="store_true",
                   help="Skip facility_ids already present in the output parquet.")
    p.add_argument("--workers", type=int, default=1,
                   help="Concurrent in-flight LLM calls (default 1). 8-12 is a good range for OpenRouter Haiku 4.5; ~5x wall-time vs. sequential.")
    p.add_argument("--tables-dir", type=str, default=None)
    p.add_argument("--model", type=str, default=DEFAULT_EXTRACTOR_MODEL)
    return p


def _cli(argv: Iterable[str] | None = None) -> None:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    main(
        subset=args.subset,
        limit=args.limit,
        start_index=args.start_index,
        flush_every=args.flush_every,
        resume=args.resume,
        workers=args.workers,
        tables_dir=args.tables_dir,
        model=args.model,
    )


if __name__ == "__main__":  # pragma: no cover
    _cli()


# ``nullcontext`` retained as a safety import for callers that monkeypatch
# ``_maybe_mlflow_span`` with a no-op factory.
__all__ = ["main", "ExtractedCapabilities", "nullcontext"]
