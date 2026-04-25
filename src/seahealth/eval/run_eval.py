"""End-to-end Naomi gold-eval runner.

Reads Naomi's hand-labeled CSV, the extractor's capability predictions
(parquet or JSON), and the validator's audits/contradictions (parquet or
JSON), then emits a markdown report of capability + contradiction
precision/recall/F1.

Designed so it can be re-run unchanged once Naomi delivers a populated
CSV — only the input file path needs to change.

Usage:

    python -m seahealth.eval.run_eval \\
        --labels docs/tasks/naomi_labeling_template.csv \\
        --output docs/eval/naomi_run.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from seahealth.eval.metrics import (
    BinaryMetrics,
    compute_capability_metrics,
    compute_contradiction_metrics,
)
from seahealth.eval.naomi_mapping import (
    UNMAPPED_CAPABILITY_VALUES,
    UNMAPPED_CONTRADICTION_VALUES,
    is_contradiction_label,
    map_capability,
    map_contradiction,
)
from seahealth.schemas import CapabilityType, ContradictionType

DEFAULT_EXTRACTIONS_PARQUET = "tables/capabilities.parquet"
DEFAULT_AUDITS_PARQUET = "tables/facility_audits.parquet"
DEFAULT_OUTPUT_MD = "docs/eval/naomi_run.md"

REQUIRED_LABEL_COLUMNS = (
    "facility_id",
    "claimed_capability",
    "evidence_status",
    "contradiction_type",
)


def _read_labels(labels_csv: str) -> pd.DataFrame:
    path = Path(labels_csv)
    if not path.exists():
        raise FileNotFoundError(
            f"Naomi labels CSV not found: {labels_csv}. "
            "Expected the populated template at docs/tasks/naomi_labeling_template.csv."
        )
    df = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in REQUIRED_LABEL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Naomi labels CSV {labels_csv} is missing required columns: {missing}. "
            f"Got columns: {list(df.columns)}"
        )
    return df


def _read_extractions(
    path: str | None,
) -> list[tuple[str, CapabilityType]]:
    """Return (facility_id, CapabilityType) pairs from extractor output.

    Accepts JSON (list of {facility_id, capability_type}) or Parquet with
    columns ``facility_id``, ``capability_type``. Filters to only ``claimed=True``
    rows when that column is present.
    """
    if path is None:
        path = DEFAULT_EXTRACTIONS_PARQUET
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Extractions not found: {path}. "
            "Run the extractor pipeline first or pass --extractions <path>. "
            "Expected JSON list[{facility_id, capability_type}] or Parquet with those columns."
        )
    if p.suffix == ".json":
        with open(p) as fh:
            raw = json.load(fh)
        if isinstance(raw, dict) and "capabilities" in raw:
            raw = raw["capabilities"]
        df = pd.DataFrame(raw)
    else:
        df = pd.read_parquet(p)
    if "claimed" in df.columns:
        df = df[df["claimed"].astype(bool)]
    out: list[tuple[str, CapabilityType]] = []
    for _, row in df.iterrows():
        cap_str = str(row["capability_type"])
        try:
            cap = CapabilityType(cap_str)
        except ValueError:
            continue
        out.append((str(row["facility_id"]), cap))
    return out


def _read_audits(
    path: str | None,
) -> list[tuple[str, CapabilityType, ContradictionType]]:
    """Return (facility_id, CapabilityType, ContradictionType) triples.

    Accepts JSON (list of {facility_id, capability_type, contradictions:[...]}
    where each contradiction is a string) or Parquet with the same shape.
    Returns one row per (facility, capability, contradiction_type).
    """
    if path is None:
        path = DEFAULT_AUDITS_PARQUET
    p = Path(path)
    if not p.exists():
        # Audits are optional — without them, contradiction metrics fall back
        # to "no predicted positives".
        return []
    if p.suffix == ".json":
        with open(p) as fh:
            raw = json.load(fh)
        if isinstance(raw, dict) and "audits" in raw:
            raw = raw["audits"]
    else:
        raw = pd.read_parquet(p).to_dict(orient="records")

    out: list[tuple[str, CapabilityType, ContradictionType]] = []
    for row in raw:
        try:
            cap = CapabilityType(str(row["capability_type"]))
        except (KeyError, ValueError):
            continue
        contras = row.get("contradictions") or []
        if not contras:
            continue
        for c in contras:
            try:
                ctype = ContradictionType(str(c))
            except ValueError:
                continue
            out.append((str(row["facility_id"]), cap, ctype))
    return out


def _per_capability_breakdown(
    expected_pairs: set[tuple[str, CapabilityType]],
    predicted_pairs: set[tuple[str, CapabilityType]],
) -> dict[str, BinaryMetrics]:
    """Per-CapabilityType TP/FP/FN restricted to mapped Naomi rows."""
    by_cap_expected: dict[CapabilityType, set[str]] = defaultdict(set)
    by_cap_predicted: dict[CapabilityType, set[str]] = defaultdict(set)
    for fid, cap in expected_pairs:
        by_cap_expected[cap].add(fid)
    for fid, cap in predicted_pairs:
        by_cap_predicted[cap].add(fid)

    out: dict[str, BinaryMetrics] = {}
    for cap in sorted(set(by_cap_expected) | set(by_cap_predicted), key=lambda c: c.value):
        e = by_cap_expected.get(cap, set())
        p = by_cap_predicted.get(cap, set())
        tp = len(e & p)
        fp = len(p - e)
        fn = len(e - p)
        out[cap.value] = BinaryMetrics(tp=tp, fp=fp, fn=fn, tn=0)
    return out


def _render_markdown(
    *,
    labels_csv: str,
    n_labels: int,
    n_facilities: int,
    capability_metrics: BinaryMetrics,
    contradiction_metrics: BinaryMetrics,
    per_capability: dict[str, BinaryMetrics],
    unmapped_capability_rows: int,
    unmapped_contradiction_rows: int,
) -> str:
    lines: list[str] = []
    lines.append("# Naomi Gold Eval Run")
    lines.append("")
    lines.append(
        f"This report compares Naomi's hand-labeled facilities (`{labels_csv}`) "
        "against the extractor + validator output."
    )
    lines.append("")
    lines.append(f"- Labeled rows: **{n_labels}** across **{n_facilities}** facilities")
    lines.append(f"- Capability rows that didn't map cleanly: **{unmapped_capability_rows}**")
    lines.append(
        f"- Contradiction rows whose type didn't map cleanly: **{unmapped_contradiction_rows}**"
    )
    lines.append("")
    lines.append("## Mapping limitations")
    lines.append("")
    lines.append(
        "The following Naomi values are intentionally not mapped to our closed enums. "
        "Rows that use them are excluded from precision/recall on the affected metric "
        "but are surfaced here so they don't disappear silently."
    )
    lines.append("")
    cap_unmapped = ", ".join(sorted(UNMAPPED_CAPABILITY_VALUES)) or "(none)"
    contra_unmapped = ", ".join(sorted(UNMAPPED_CONTRADICTION_VALUES)) or "(none)"
    lines.append(f"- Capabilities without a clean enum target: {cap_unmapped}")
    lines.append(f"- Contradiction types without a clean enum target: {contra_unmapped}")
    lines.append("")
    lines.append("## Capability extraction")
    lines.append("")
    lines.append(f"- Precision: **{capability_metrics.precision:.3f}**")
    lines.append(f"- Recall: **{capability_metrics.recall:.3f}**")
    lines.append(f"- F1: **{capability_metrics.f1:.3f}**")
    lines.append(
        f"- TP={capability_metrics.tp} FP={capability_metrics.fp} FN={capability_metrics.fn}"
    )
    lines.append("")
    lines.append("## Contradiction detection")
    lines.append("")
    lines.append(f"- Precision: **{contradiction_metrics.precision:.3f}**")
    lines.append(f"- Recall: **{contradiction_metrics.recall:.3f}**")
    lines.append(f"- F1: **{contradiction_metrics.f1:.3f}**")
    lines.append(
        f"- TP={contradiction_metrics.tp} "
        f"FP={contradiction_metrics.fp} "
        f"FN={contradiction_metrics.fn} "
        f"TN={contradiction_metrics.tn}"
    )
    lines.append("")
    lines.append("## Per-capability breakdown")
    lines.append("")
    if per_capability:
        lines.append("| Capability | TP | FP | FN | Precision | Recall | F1 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for cap, m in per_capability.items():
            lines.append(
                f"| {cap} | {m.tp} | {m.fp} | {m.fn} | "
                f"{m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} |"
            )
    else:
        lines.append("(no rows)")
    lines.append("")
    return "\n".join(lines)


def _maybe_log_mlflow(metrics: dict[str, Any]) -> None:
    if not os.getenv("MLFLOW_TRACKING_URI"):
        return
    try:
        import mlflow
    except ImportError:
        return
    mlflow.set_experiment("seahealth/eval-naomi")
    with mlflow.start_run():
        for k, v in metrics.items():
            if isinstance(v, (int, float)):
                mlflow.log_metric(k, float(v))


def main(
    labels_csv: str,
    extractions_path: str | None = None,
    audits_path: str | None = None,
    output_md: str | None = DEFAULT_OUTPUT_MD,
    log_mlflow: bool = False,
) -> dict[str, Any]:
    """Run the eval and (optionally) write a markdown report.

    Returns a dict suitable for programmatic consumption (status, metrics).
    """
    df = _read_labels(labels_csv)
    if df.empty:
        result = {
            "status": "no_labels",
            "labels_csv": labels_csv,
            "message": "Labels CSV is empty (likely the unfilled template). No metrics computed.",
        }
        if output_md:
            Path(output_md).parent.mkdir(parents=True, exist_ok=True)
            Path(output_md).write_text(
                "# Naomi Gold Eval Run\n\n"
                f"Last run: empty labels CSV at `{labels_csv}`. "
                "Re-run once Naomi delivers populated labels.\n"
            )
        return result

    # Build the (facility, naomi_capability) and (..., contradiction) lists.
    expected_cap = list(
        zip(
            df["facility_id"].astype(str),
            df["claimed_capability"].astype(str),
            strict=True,
        )
    )
    expected_contra = list(
        zip(
            df["facility_id"].astype(str),
            df["claimed_capability"].astype(str),
            df["contradiction_type"].astype(str),
            strict=True,
        )
    )
    predicted_cap = _read_extractions(extractions_path)
    predicted_contra = _read_audits(audits_path)

    capability_metrics = compute_capability_metrics(expected_cap, predicted_cap)
    contradiction_metrics = compute_contradiction_metrics(expected_contra, predicted_contra)

    # Build per-capability breakdown over the mapped expected/predicted pairs.
    expected_pairs: set[tuple[str, CapabilityType]] = set()
    for fid, naomi_cap in expected_cap:
        mapped = map_capability(naomi_cap)
        if mapped is not None:
            expected_pairs.add((fid, mapped))
    predicted_pairs = set(predicted_cap)
    per_capability = _per_capability_breakdown(expected_pairs, predicted_pairs)

    unmapped_cap_rows = sum(
        1 for _, naomi_cap in expected_cap if map_capability(naomi_cap) is None
    )
    unmapped_contra_rows = sum(
        1
        for _, _, naomi_contra in expected_contra
        if is_contradiction_label(naomi_contra) and map_contradiction(naomi_contra) is None
    )

    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(
            _render_markdown(
                labels_csv=labels_csv,
                n_labels=len(df),
                n_facilities=df["facility_id"].nunique(),
                capability_metrics=capability_metrics,
                contradiction_metrics=contradiction_metrics,
                per_capability=per_capability,
                unmapped_capability_rows=unmapped_cap_rows,
                unmapped_contradiction_rows=unmapped_contra_rows,
            )
        )

    flat = {
        "status": "ok",
        "labels_csv": labels_csv,
        "n_labels": len(df),
        "n_facilities": int(df["facility_id"].nunique()),
        "capability_precision": capability_metrics.precision,
        "capability_recall": capability_metrics.recall,
        "capability_f1": capability_metrics.f1,
        "capability_tp": capability_metrics.tp,
        "capability_fp": capability_metrics.fp,
        "capability_fn": capability_metrics.fn,
        "contradiction_precision": contradiction_metrics.precision,
        "contradiction_recall": contradiction_metrics.recall,
        "contradiction_f1": contradiction_metrics.f1,
        "contradiction_tp": contradiction_metrics.tp,
        "contradiction_fp": contradiction_metrics.fp,
        "contradiction_fn": contradiction_metrics.fn,
        "unmapped_capability_rows": unmapped_cap_rows,
        "unmapped_contradiction_rows": unmapped_contra_rows,
        "per_capability": {k: v.to_dict() for k, v in per_capability.items()},
    }
    if log_mlflow:
        _maybe_log_mlflow(flat)
    return flat


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="seahealth.eval.run_eval",
        description="Score the extractor + validator against Naomi's hand-labeled gold set.",
    )
    p.add_argument(
        "--labels",
        required=True,
        help="Path to Naomi's labels CSV (e.g. docs/tasks/naomi_labeling_template.csv).",
    )
    p.add_argument(
        "--extractions",
        default=None,
        help=f"Capabilities parquet/JSON. Default: {DEFAULT_EXTRACTIONS_PARQUET} if it exists.",
    )
    p.add_argument(
        "--audits",
        default=None,
        help=f"Audits parquet/JSON. Default: {DEFAULT_AUDITS_PARQUET} if it exists.",
    )
    p.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_MD,
        help=f"Markdown report path. Default: {DEFAULT_OUTPUT_MD}.",
    )
    p.add_argument(
        "--log-mlflow",
        action="store_true",
        help="If set and MLFLOW_TRACKING_URI is configured, log metrics to MLflow.",
    )
    return p


def cli(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    try:
        result = main(
            labels_csv=args.labels,
            extractions_path=args.extractions,
            audits_path=args.audits,
            output_md=args.output,
            log_mlflow=args.log_mlflow,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if result.get("status") == "no_labels":
        print("no labels yet — leaving placeholder report at", args.output)
        return 0
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
