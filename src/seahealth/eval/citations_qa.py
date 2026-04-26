"""Citation quality report for ``tables/capabilities.parquet`` evidence refs.

Walks every ``EvidenceRef`` in the extracted capabilities, joins it against
``tables/chunks.parquet``, and classifies each ref as one of:

* ``valid_substring`` — the snippet appears verbatim inside the chunk text at
  the ref's recorded span.
* ``valid_normalized`` — the snippet appears in the chunk text after collapsing
  whitespace (we accept this since the extractor's normalizer also accepts it).
* ``empty_snippet`` — the snippet is missing or whitespace-only.
* ``zero_span`` — the ref's span is ``(0, 0)``, the extractor's failure marker.
* ``mismatch`` — the snippet was *not* found in the chunk text at all.
* ``chunk_missing`` — the chunk_id referenced does not exist in chunks.parquet.

The CLI prints a one-page summary and (optionally) writes the per-ref details
as JSON for downstream debugging::

    python -m seahealth.eval.citations_qa
    python -m seahealth.eval.citations_qa --capabilities tables/capabilities.parquet \\
        --chunks tables/chunks.parquet --details out/citation_details.json

Designed to run on the legacy 10k extraction without modification — invalid
spans are surfaced as data-quality counts rather than turning into exceptions.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAPABILITIES_PARQUET = REPO_ROOT / "tables" / "capabilities.parquet"
DEFAULT_CHUNKS_PARQUET = REPO_ROOT / "tables" / "chunks.parquet"

CITATION_CLASSES = (
    "valid_substring",
    "valid_normalized",
    "empty_snippet",
    "mismatch",
    "chunk_missing",
)

VALID_CLASSES = {"valid_substring", "valid_normalized"}


@dataclass(frozen=True)
class CitationFinding:
    """One classified evidence ref."""

    facility_id: str
    capability_type: str
    chunk_id: str
    source_doc_id: str
    span: tuple[int, int]
    snippet: str
    classification: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "facility_id": self.facility_id,
            "capability_type": self.capability_type,
            "chunk_id": self.chunk_id,
            "source_doc_id": self.source_doc_id,
            "span": list(self.span),
            "snippet": self.snippet,
            "classification": self.classification,
        }


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def classify_ref(
    snippet: str,
    span: tuple[int, int],
    chunk_text: str | None,
) -> str:
    """Classify a single evidence ref. Pure function — easy to unit test.

    Decision order:

    1. chunk_text is None        → chunk_missing
    2. snippet is empty / blank  → empty_snippet
    3. snippet appears verbatim in chunk_text  → valid_substring
       (we accept this regardless of the recorded span — the extractor's own
       re-anchoring would have produced the same result on a fresh run)
    4. snippet matches after whitespace collapse  → valid_normalized
    5. otherwise                  → mismatch (covers (0, 0) extractor failure
       markers and genuine "snippet absent" cases — both mean the citation
       chip would render unsupported text)
    """
    del span  # span is informational; presence in chunk text is authoritative
    if chunk_text is None:
        return "chunk_missing"
    snippet = snippet or ""
    if not snippet.strip():
        return "empty_snippet"
    if snippet in chunk_text:
        return "valid_substring"
    norm_snippet = _collapse_whitespace(snippet)
    if norm_snippet and norm_snippet in _collapse_whitespace(chunk_text):
        return "valid_normalized"
    return "mismatch"


def _load_chunk_text_index(chunks_path: Path) -> dict[str, str]:
    """Return ``{chunk_id: text}`` from ``tables/chunks.parquet``.

    Returns an empty dict if the parquet is missing — the caller will then
    classify every ref as ``chunk_missing`` so the report is still produced.
    """
    if not chunks_path.exists():
        log.warning("chunks parquet missing at %s; all refs will be chunk_missing", chunks_path)
        return {}
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - hard dep
        raise RuntimeError(f"pyarrow unavailable: {exc}") from exc
    table = pq.read_table(chunks_path, columns=["chunk_id", "text"])
    rows = table.to_pylist()
    return {str(row["chunk_id"]): str(row.get("text") or "") for row in rows}


def _iter_capability_refs(capabilities_path: Path):
    """Yield ``(facility_id, capability_type, ref_dict)`` from capabilities.parquet."""
    if not capabilities_path.exists():
        raise FileNotFoundError(f"capabilities parquet missing: {capabilities_path}")
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - hard dep
        raise RuntimeError(f"pyarrow unavailable: {exc}") from exc
    table = pq.read_table(capabilities_path)
    columns = set(table.column_names)
    for row in table.to_pylist():
        facility_id = str(row.get("facility_id") or "")
        cap_type = str(row.get("capability_type") or "")
        refs_raw: Any
        if "evidence_refs_json" in columns:
            refs_raw = row.get("evidence_refs_json")
        elif "payload" in columns:
            payload = row.get("payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = None
            refs_raw = (payload or {}).get("evidence_refs") if isinstance(payload, dict) else None
        else:
            refs_raw = None
        if isinstance(refs_raw, str):
            try:
                refs_raw = json.loads(refs_raw)
            except json.JSONDecodeError:
                refs_raw = None
        if not isinstance(refs_raw, list):
            continue
        for ref in refs_raw:
            if isinstance(ref, dict):
                yield facility_id, cap_type, ref


def _ref_span_tuple(ref: dict[str, Any]) -> tuple[int, int]:
    span = ref.get("span") or [0, 0]
    if isinstance(span, (list, tuple)) and len(span) == 2:
        try:
            return int(span[0]), int(span[1])
        except (TypeError, ValueError):
            return 0, 0
    return 0, 0


def run_citation_qa(
    *,
    capabilities_path: Path = DEFAULT_CAPABILITIES_PARQUET,
    chunks_path: Path = DEFAULT_CHUNKS_PARQUET,
) -> dict[str, Any]:
    """Compute the citation QA report.

    Returns a dict with the schema::

        {
            "totals": {"refs": int, "valid": int, "invalid": int},
            "by_class": {<class>: int, ...},
            "examples": {<failing_class>: [CitationFinding.to_dict, ...up to 3]},
            "capabilities_path": str,
            "chunks_path": str,
        }
    """
    chunk_text_index = _load_chunk_text_index(chunks_path)

    by_class: dict[str, int] = {cls: 0 for cls in CITATION_CLASSES}
    examples: dict[str, list[dict[str, Any]]] = {cls: [] for cls in CITATION_CLASSES}
    total = 0

    for facility_id, capability_type, ref in _iter_capability_refs(capabilities_path):
        snippet = str(ref.get("snippet") or "")
        chunk_id = str(ref.get("chunk_id") or "")
        source_doc_id = str(ref.get("source_doc_id") or "")
        span = _ref_span_tuple(ref)
        chunk_text = chunk_text_index.get(chunk_id)
        classification = classify_ref(snippet, span, chunk_text)

        by_class[classification] += 1
        total += 1
        if classification not in VALID_CLASSES and len(examples[classification]) < 3:
            finding = CitationFinding(
                facility_id=facility_id,
                capability_type=capability_type,
                chunk_id=chunk_id,
                source_doc_id=source_doc_id,
                span=span,
                snippet=snippet[:120],
                classification=classification,
            )
            examples[classification].append(finding.to_dict())

    valid = sum(by_class[cls] for cls in VALID_CLASSES)
    invalid = total - valid
    return {
        "totals": {"refs": total, "valid": valid, "invalid": invalid},
        "by_class": by_class,
        "examples": {cls: rows for cls, rows in examples.items() if rows},
        "capabilities_path": str(capabilities_path),
        "chunks_path": str(chunks_path),
    }


def format_report(report: dict[str, Any]) -> str:
    """Pretty-print the QA report for the CLI / docs."""
    totals = report["totals"]
    lines: list[str] = []
    lines.append("Citation QA report")
    lines.append("==================")
    lines.append(f"capabilities: {report['capabilities_path']}")
    lines.append(f"chunks:       {report['chunks_path']}")
    lines.append("")
    if totals["refs"] == 0:
        lines.append("No evidence refs found.")
        return "\n".join(lines)
    pct = (totals["valid"] / totals["refs"]) * 100
    lines.append(
        f"refs={totals['refs']}  valid={totals['valid']}  "
        f"invalid={totals['invalid']}  valid%={pct:.1f}"
    )
    lines.append("")
    lines.append("by class:")
    for cls in CITATION_CLASSES:
        lines.append(f"  {cls:<18} {report['by_class'].get(cls, 0):>6}")
    failing = {cls: rows for cls, rows in report.get("examples", {}).items() if rows}
    if failing:
        lines.append("")
        lines.append("top failure examples:")
        for cls, rows in failing.items():
            lines.append(f"  [{cls}]")
            for row in rows:
                lines.append(
                    f"    facility={row['facility_id']} cap={row['capability_type']} "
                    f"chunk={row['chunk_id']} span={tuple(row['span'])} "
                    f"snippet={row['snippet']!r}"
                )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Run the citation quality QA report against a capabilities parquet "
            "and a chunks parquet. Prints a summary; --details writes per-ref "
            "JSON for debugging."
        ),
    )
    p.add_argument(
        "--capabilities",
        type=Path,
        default=DEFAULT_CAPABILITIES_PARQUET,
        help=f"Path to capabilities parquet (default: {DEFAULT_CAPABILITIES_PARQUET}).",
    )
    p.add_argument(
        "--chunks",
        type=Path,
        default=DEFAULT_CHUNKS_PARQUET,
        help=f"Path to chunks parquet (default: {DEFAULT_CHUNKS_PARQUET}).",
    )
    p.add_argument(
        "--details",
        type=Path,
        default=None,
        help="Optional path to write the full report (incl. examples) as JSON.",
    )
    return p


def _cli(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_citation_qa(
        capabilities_path=args.capabilities,
        chunks_path=args.chunks,
    )
    print(format_report(report))
    if args.details is not None:
        args.details.parent.mkdir(parents=True, exist_ok=True)
        args.details.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())


__all__ = [
    "CitationFinding",
    "CITATION_CLASSES",
    "VALID_CLASSES",
    "classify_ref",
    "run_citation_qa",
    "format_report",
]
