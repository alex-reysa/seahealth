"""Adapt Naomi's hand-labeled xlsx into the CSV shape `run_eval` expects.

Naomi's file (``india_health_facilities_check_labels_final_v2.xlsx``) has:
  * ``source_row_number`` (1-indexed into the original VF dataset)
  * ``claimed_capability`` as semicolon-separated multi-value strings
  * ``evidence_status`` extended with ``unclear`` / ``silent``
  * NO ``facility_id`` column

`run_eval._read_labels` requires a CSV with columns ``facility_id``,
``claimed_capability`` (single-valued), ``evidence_status``, ``contradiction_type``.

This adapter:
  1. Reads the xlsx ``labels`` sheet.
  2. Joins ``source_row_number`` (1-indexed) ↔ ``facilities_index.row_index``
     (0-indexed) using the offset ``row_index = source_row_number - 1``.
  3. Explodes ``claimed_capability`` on ``;`` so each (facility, capability) pair
     becomes its own row — matching the eval harness's per-pair semantics.
  4. Emits a CSV at ``out_csv_path``. Rows whose source_row_number doesn't
     resolve to a known facility are dropped and reported.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_FACILITIES_INDEX_PATH = REPO_ROOT / "tables" / "facilities_index.parquet"
DEFAULT_OUT_CSV_PATH = REPO_ROOT / "tables" / "naomi_labels.csv"


def adapt_naomi_xlsx(
    xlsx_path: str | Path,
    facilities_index_path: str | Path = DEFAULT_FACILITIES_INDEX_PATH,
    out_csv_path: str | Path = DEFAULT_OUT_CSV_PATH,
    sheet_name: str = "labels",
) -> dict:
    """Read Naomi's xlsx, derive ``facility_id`` per row, explode multi-value
    capabilities, write the eval-ready CSV.

    Returns a small summary dict with row counts and any warnings. Raises
    ``FileNotFoundError`` if either input path is missing.
    """
    xlsx = Path(xlsx_path)
    fi_path = Path(facilities_index_path)
    out = Path(out_csv_path)
    if not xlsx.exists():
        raise FileNotFoundError(f"Naomi xlsx not found: {xlsx}")
    if not fi_path.exists():
        raise FileNotFoundError(
            f"facilities_index.parquet not found: {fi_path}. "
            "Run `python -m seahealth.pipelines.normalize` first."
        )

    raw = pd.read_excel(xlsx, sheet_name=sheet_name)
    raw_rows = len(raw)

    # Required columns we depend on.
    required = {
        "source_row_number",
        "claimed_capability",
        "evidence_status",
        "contradiction_type",
    }
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(
            f"Naomi xlsx {xlsx} missing required columns: {sorted(missing)}. "
            f"Got: {list(raw.columns)}"
        )

    # Coerce source_row_number to int (drops blanks).
    raw["source_row_number"] = pd.to_numeric(
        raw["source_row_number"], errors="coerce"
    ).astype("Int64")
    blank_rows = raw["source_row_number"].isna().sum()
    raw = raw.dropna(subset=["source_row_number"])

    # Naomi's source_row_number is 1-indexed; our row_index is 0-indexed.
    raw["row_index"] = (raw["source_row_number"].astype("int64") - 1)

    # Join to facilities_index → facility_id. Inner join drops unresolved rows.
    fi = pd.read_parquet(fi_path, columns=["facility_id", "row_index", "name", "address_city"])
    joined = raw.merge(fi, on="row_index", how="left")
    unresolved = joined["facility_id"].isna().sum()
    if unresolved:
        unresolved_ids = joined.loc[joined["facility_id"].isna(), "source_row_number"].tolist()
        logger.warning(
            "Dropped %d Naomi rows with unresolvable source_row_number(s): %s",
            unresolved,
            unresolved_ids,
        )
    joined = joined.dropna(subset=["facility_id"])

    # Explode the multi-value claimed_capability on ';' so each (facility,
    # capability) pair becomes its own row.
    joined["claimed_capability"] = (
        joined["claimed_capability"]
        .astype(str)
        .str.split(";")
        .apply(lambda items: [s.strip() for s in items if s and s.strip()])
    )
    joined = joined.explode("claimed_capability", ignore_index=True)
    joined = joined[joined["claimed_capability"].astype(bool)]

    # Final shape: only the columns run_eval needs + a couple useful for
    # debugging the report. The harness ignores extras.
    out_cols = [
        "facility_id",
        "claimed_capability",
        "evidence_status",
        "contradiction_type",
        "source_row_number",
        "name",
        "address_city",
    ]
    final = joined[out_cols].copy()
    # Normalize evidence_status / contradiction_type to lowercase (Naomi's xlsx
    # is consistent already, but defensive).
    final["evidence_status"] = final["evidence_status"].astype(str).str.strip().str.lower()
    final["contradiction_type"] = (
        final["contradiction_type"].astype(str).str.strip().str.lower()
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(out, index=False)

    return {
        "input_xlsx": str(xlsx),
        "input_rows": int(raw_rows),
        "blank_source_row_number": int(blank_rows),
        "unresolved_facility_ids": int(unresolved),
        "exploded_rows": int(len(final)),
        "unique_facilities": int(final["facility_id"].nunique()),
        "unique_capabilities": int(final["claimed_capability"].nunique()),
        "output_csv": str(out),
    }


def main(argv: list[str] | None = None) -> None:
    import argparse

    p = argparse.ArgumentParser(description="Adapt Naomi's xlsx → eval-ready CSV.")
    p.add_argument("--xlsx", required=True, help="Path to Naomi's xlsx file.")
    p.add_argument(
        "--facilities-index",
        default=str(DEFAULT_FACILITIES_INDEX_PATH),
        help="Path to tables/facilities_index.parquet.",
    )
    p.add_argument(
        "--out",
        default=str(DEFAULT_OUT_CSV_PATH),
        help="Output CSV path (default: tables/naomi_labels.csv).",
    )
    args = p.parse_args(argv)
    summary = adapt_naomi_xlsx(args.xlsx, args.facilities_index, args.out)
    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
