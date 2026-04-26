"""Tests for ``seahealth.eval.naomi_label_adapter``.

Verifies:
  * 1-indexed → 0-indexed offset between Naomi's source_row_number and our row_index
  * multi-value `claimed_capability` (semicolon-separated) explodes one row per cap
  * unresolved source_row_numbers are dropped (and reported in the summary)
  * `unclear` / `silent` evidence_status values pass through unchanged
  * resulting CSV has every column `run_eval._read_labels` requires
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seahealth.eval.naomi_label_adapter import adapt_naomi_xlsx
from seahealth.eval.run_eval import REQUIRED_LABEL_COLUMNS


def _write_facilities_index(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame.from_records(rows)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _write_xlsx(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame.from_records(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="labels", index=False)


@pytest.fixture
def tiny_facilities_index(tmp_path: Path) -> Path:
    path = tmp_path / "facilities_index.parquet"
    _write_facilities_index(
        path,
        [
            {"facility_id": "vf_02163_child-s-life-hospital",
             "row_index": 2163, "name": "Child's Life Hospital",
             "address_city": "Sitamarhi"},
            {"facility_id": "vf_05000_some-clinic",
             "row_index": 5000, "name": "Some Clinic",
             "address_city": "Patna"},
            {"facility_id": "vf_07000_x-ray-centre",
             "row_index": 7000, "name": "X-Ray Centre",
             "address_city": "Gaya"},
        ],
    )
    return path


def test_offset_naomi_1indexed_to_our_0indexed(tmp_path, tiny_facilities_index):
    """source_row_number=2164 must resolve to row_index=2163."""
    xlsx = tmp_path / "labels.xlsx"
    _write_xlsx(xlsx, [
        {
            "source_row_number": 2164,
            "claimed_capability": "neonatal",
            "evidence_status": "contradicts",
            "contradiction_type": "capability_equipment_mismatch",
        }
    ])
    out = tmp_path / "out.csv"

    summary = adapt_naomi_xlsx(xlsx, tiny_facilities_index, out)

    assert summary["unresolved_facility_ids"] == 0
    assert summary["exploded_rows"] == 1
    df = pd.read_csv(out)
    assert df.iloc[0]["facility_id"] == "vf_02163_child-s-life-hospital"


def test_multi_value_capability_explodes_into_separate_rows(
    tmp_path, tiny_facilities_index
):
    xlsx = tmp_path / "labels.xlsx"
    _write_xlsx(xlsx, [
        {
            "source_row_number": 2164,
            "claimed_capability": "neonatal;emergency_trauma;icu",
            "evidence_status": "contradicts",
            "contradiction_type": "capability_equipment_mismatch",
        }
    ])
    out = tmp_path / "out.csv"
    summary = adapt_naomi_xlsx(xlsx, tiny_facilities_index, out)
    df = pd.read_csv(out)

    assert summary["exploded_rows"] == 3
    assert sorted(df["claimed_capability"].tolist()) == [
        "emergency_trauma",
        "icu",
        "neonatal",
    ]
    # Same source row should yield same facility_id across all exploded rows.
    assert df["facility_id"].nunique() == 1


def test_unresolved_source_row_number_is_dropped(tmp_path, tiny_facilities_index):
    """Naomi rows whose source_row_number isn't in our facilities_index get
    dropped — surfaced in the summary so the operator can re-extract."""
    xlsx = tmp_path / "labels.xlsx"
    _write_xlsx(xlsx, [
        {
            "source_row_number": 2164,
            "claimed_capability": "neonatal",
            "evidence_status": "contradicts",
            "contradiction_type": "capability_equipment_mismatch",
        },
        {
            "source_row_number": 999999,  # not in our index
            "claimed_capability": "icu",
            "evidence_status": "supports",
            "contradiction_type": "none",
        },
    ])
    out = tmp_path / "out.csv"

    summary = adapt_naomi_xlsx(xlsx, tiny_facilities_index, out)

    assert summary["unresolved_facility_ids"] == 1
    assert summary["exploded_rows"] == 1
    df = pd.read_csv(out)
    assert len(df) == 1
    assert df.iloc[0]["facility_id"] == "vf_02163_child-s-life-hospital"


def test_evidence_status_extras_pass_through(tmp_path, tiny_facilities_index):
    xlsx = tmp_path / "labels.xlsx"
    _write_xlsx(xlsx, [
        {
            "source_row_number": 5001,
            "claimed_capability": "icu",
            "evidence_status": "unclear",
            "contradiction_type": "vague_claim",
        },
        {
            "source_row_number": 7001,
            "claimed_capability": "dialysis",
            "evidence_status": "silent",
            "contradiction_type": "none",
        },
    ])
    out = tmp_path / "out.csv"

    adapt_naomi_xlsx(xlsx, tiny_facilities_index, out)
    df = pd.read_csv(out)
    assert sorted(df["evidence_status"].tolist()) == ["silent", "unclear"]


def test_output_csv_has_columns_run_eval_requires(tmp_path, tiny_facilities_index):
    xlsx = tmp_path / "labels.xlsx"
    _write_xlsx(xlsx, [
        {
            "source_row_number": 2164,
            "claimed_capability": "neonatal",
            "evidence_status": "contradicts",
            "contradiction_type": "capability_equipment_mismatch",
        }
    ])
    out = tmp_path / "out.csv"
    adapt_naomi_xlsx(xlsx, tiny_facilities_index, out)
    df = pd.read_csv(out)
    for col in REQUIRED_LABEL_COLUMNS:
        assert col in df.columns, (
            f"adapter output is missing required eval column: {col}"
        )


def test_missing_xlsx_raises_filenotfound(tmp_path, tiny_facilities_index):
    with pytest.raises(FileNotFoundError):
        adapt_naomi_xlsx(
            tmp_path / "does_not_exist.xlsx",
            tiny_facilities_index,
            tmp_path / "out.csv",
        )


def test_missing_facilities_index_raises_filenotfound(tmp_path):
    xlsx = tmp_path / "labels.xlsx"
    _write_xlsx(xlsx, [
        {
            "source_row_number": 2164,
            "claimed_capability": "neonatal",
            "evidence_status": "contradicts",
            "contradiction_type": "none",
        }
    ])
    with pytest.raises(FileNotFoundError):
        adapt_naomi_xlsx(
            xlsx,
            tmp_path / "no_such_index.parquet",
            tmp_path / "out.csv",
        )
