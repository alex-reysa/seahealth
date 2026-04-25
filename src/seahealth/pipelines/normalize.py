"""Normalize the VF facilities CSV into chunked parquet tables.

Outputs (under ``output_dir``, default ``<repo>/tables/``):

* ``chunks.parquet`` — four chunks per facility, one per :data:`SourceType`
  variant in :class:`seahealth.schemas.evidence.EvidenceRef`.
* ``facilities_index.parquet`` — facility-level lookup table (id, name,
  geo, recency, type, doctor count, capacity).
* ``demo_subset.json`` — capped allow-list of facility ids covering the
  Patna-area + surgery-keyword cohort used by the end-to-end demo.

Run via ``python -m seahealth.pipelines.normalize``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV_PATH = (
    REPO_ROOT / "VF_Hackathon_Dataset_India_Large.xlsx - VF_Hackathon_Dataset_India_Larg.csv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "tables"

PATNA_LAT = 25.61
PATNA_LNG = 85.14
PATNA_RADIUS_KM = 100.0
DEMO_SUBSET_CAP = 250

# Each chunk text gets a labeled prefix so downstream agents can locate it
# even after vector-store reordering.
SOURCE_TYPES: tuple[str, ...] = (
    "facility_note",
    "staff_roster",
    "equipment_inventory",
    "volume_report",
)

# Surgery-adjacent keywords for the demo allow-list.  Matched
# case-insensitively as substrings via ``re.search``.
SURGERY_KEYWORDS: tuple[str, ...] = (
    "appendectomy",
    "appendicitis",
    "surgery",
    "surgical",
    "general surgery",
    "laparoscop",
    "anesthesia",
    "anaesthesia",
    "operating theatre",
    "operation theater",
    "OT",
)
# ``OT`` is short and case-sensitive on purpose to avoid matching every
# word containing "ot"; everything else is lower-cased before search.
_SURGERY_LOWER = tuple(k.lower() for k in SURGERY_KEYWORDS if k != "OT")
_SURGERY_OT_PATTERN = re.compile(r"\bOT\b")
_SURGERY_LOWER_PATTERN = re.compile("|".join(re.escape(k) for k in _SURGERY_LOWER))

# Columns scanned for the keyword match.
_KEYWORD_COLUMNS: tuple[str, ...] = (
    "description",
    "procedure",
    "capability",
    "specialties",
)

# Only the facility-index parquet uses these dtypes; ``read_csv`` itself is
# called with ``dtype=str`` so that empty strings stay empty (not NaN).
PIN_CODE_RE = re.compile(r"^\d{6}$")
SLUG_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Slug used inside ``facility_id``: lowercase, ``[^a-z0-9]+`` → ``-``, capped 24."""
    slug = SLUG_RE.sub("-", (name or "").lower()).strip("-")
    return slug[:24]


def _is_blank(value: str | None) -> bool:
    """Treat the literal CSV strings ``""``, ``"null"``, ``"NULL"`` as blank."""
    if value is None:
        return True
    s = value.strip()
    if not s:
        return True
    return s.lower() in {"null", "none", "nan"}


def _coerce_text(value: str | None) -> str:
    """Render a single field for chunk text — collapses blanks to empty."""
    return "" if _is_blank(value) else value.strip()


def _parse_list_field(raw: str | None) -> list[str]:
    """Defensively parse the JSON-array-ish list strings.

    The VF CSV stores ``specialties``/``procedure``/``equipment``/``capability``
    as either ``[]``, a JSON array, or a comma-separated string.  Returns a
    cleaned list of non-empty strings.
    """
    if _is_blank(raw):
        return []
    text = raw.strip()
    # Try strict JSON first.
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    # Fall back to comma-split, stripping surrounding brackets/quotes.
    text = text.strip("[]")
    pieces = [p.strip().strip('"').strip("'") for p in text.split(",")]
    return [p for p in pieces if p and not _is_blank(p)]


def _join_list(items: Sequence[str]) -> str:
    """Render a list field for chunk text; ``(none listed)`` if empty."""
    if not items:
        return "(none listed)"
    return ", ".join(items)


def _parse_float(raw: str | None) -> float | None:
    if _is_blank(raw):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _parse_nullable_int(raw: str | None) -> int | None:
    if _is_blank(raw):
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km using the haversine formula."""
    earth_r = 6371.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * earth_r * math.asin(math.sqrt(a))


def _matches_surgery_keyword(*fields: str | None) -> bool:
    for field in fields:
        if _is_blank(field):
            continue
        text = field  # type: ignore[assignment]
        if _SURGERY_OT_PATTERN.search(text):
            return True
        if _SURGERY_LOWER_PATTERN.search(text.lower()):
            return True
    return False


def _csv_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Chunk building
# ---------------------------------------------------------------------------


def _format_chunk(source_type: str, row: dict[str, str]) -> str:
    name = _coerce_text(row.get("name"))
    facility_type = _coerce_text(row.get("facilityTypeId"))
    city = _coerce_text(row.get("address_city"))
    state = _coerce_text(row.get("address_stateOrRegion"))
    pin = _coerce_text(row.get("address_zipOrPostcode"))
    description = _coerce_text(row.get("description"))
    specialties = _join_list(_parse_list_field(row.get("specialties")))
    equipment = _join_list(_parse_list_field(row.get("equipment")))
    procedure = _join_list(_parse_list_field(row.get("procedure")))
    capability = _join_list(_parse_list_field(row.get("capability")))
    number_doctors = _coerce_text(row.get("numberDoctors")) or "(unknown)"
    affiliated_staff = _coerce_text(row.get("affiliated_staff_presence")) or "(unknown)"
    capacity = _coerce_text(row.get("capacity")) or "(unknown)"
    recency = _coerce_text(row.get("recency_of_page_update")) or "(unknown)"

    if source_type == "facility_note":
        return (
            "[FACILITY NOTE]\n"
            f"Name: {name}\n"
            f"Type: {facility_type}\n"
            f"Location: {city}, {state} {pin}\n"
            f"Description: {description}\n"
            f"Specialties: {specialties}"
        )
    if source_type == "staff_roster":
        return (
            "[STAFF ROSTER]\n"
            f"Number of doctors: {number_doctors}\n"
            f"Affiliated staff presence: {affiliated_staff}\n"
            f"Capacity (beds): {capacity}"
        )
    if source_type == "equipment_inventory":
        return f"[EQUIPMENT INVENTORY]\nEquipment items: {equipment}"
    if source_type == "volume_report":
        return (
            "[VOLUME REPORT]\n"
            f"Capacity (beds): {capacity}\n"
            f"Claimed capabilities: {capability}\n"
            f"Claimed procedures: {procedure}\n"
            f"Most recent page update: {recency}"
        )
    raise ValueError(f"Unknown source_type {source_type!r}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _read_csv(path: Path, limit: int | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if limit is not None:
        df = df.head(limit).copy()
    df.reset_index(drop=True, inplace=True)
    return df


def _build_chunks(df: pd.DataFrame, indexed_at: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row_index, row in enumerate(df.to_dict(orient="records")):
        name = _coerce_text(row.get("name"))
        facility_id = f"vf_{row_index:05d}_{_slugify(name)}"
        for source_type in SOURCE_TYPES:
            text = _format_chunk(source_type, row)
            rows.append(
                {
                    "chunk_id": f"{facility_id}::{source_type}",
                    "facility_id": facility_id,
                    "row_index": row_index,
                    "source_type": source_type,
                    "source_doc_id": facility_id,
                    "text": text,
                    "span_start": 0,
                    "span_end": len(text),
                    "indexed_at": indexed_at,
                }
            )
    chunks = pd.DataFrame.from_records(
        rows,
        columns=[
            "chunk_id",
            "facility_id",
            "row_index",
            "source_type",
            "source_doc_id",
            "text",
            "span_start",
            "span_end",
            "indexed_at",
        ],
    )
    return chunks


def _build_facilities_index(df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for row_index, row in enumerate(df.to_dict(orient="records")):
        name = _coerce_text(row.get("name"))
        facility_id = f"vf_{row_index:05d}_{_slugify(name)}"
        pin_raw = _coerce_text(row.get("address_zipOrPostcode"))
        pin_code = pin_raw if PIN_CODE_RE.match(pin_raw) else None
        records.append(
            {
                "facility_id": facility_id,
                "row_index": row_index,
                "name": name,
                "address_city": _coerce_text(row.get("address_city")) or None,
                "address_stateOrRegion": _coerce_text(row.get("address_stateOrRegion")) or None,
                "pin_code": pin_code,
                "latitude": _parse_float(row.get("latitude")),
                "longitude": _parse_float(row.get("longitude")),
                "recency_of_page_update": _coerce_text(row.get("recency_of_page_update")) or None,
                "facilityTypeId": _coerce_text(row.get("facilityTypeId")) or None,
                "numberDoctors": _parse_nullable_int(row.get("numberDoctors")),
                "capacity": _parse_nullable_int(row.get("capacity")),
            }
        )
    facilities = pd.DataFrame.from_records(records)
    # Coerce nullable Int64 columns explicitly (pandas keeps them object otherwise).
    facilities["numberDoctors"] = facilities["numberDoctors"].astype("Int64")
    facilities["capacity"] = facilities["capacity"].astype("Int64")
    facilities["row_index"] = facilities["row_index"].astype("Int64")
    facilities["latitude"] = facilities["latitude"].astype("float64")
    facilities["longitude"] = facilities["longitude"].astype("float64")
    return facilities


def _build_demo_subset(
    df: pd.DataFrame,
    facilities: pd.DataFrame,
    csv_sha: str,
    *,
    cap: int = DEMO_SUBSET_CAP,
) -> dict[str, object]:
    """Pick facilities within 100 km of Patna OR matching a surgery keyword."""
    candidates: list[tuple[float, int, str]] = []  # (patna_distance, row_index, facility_id)
    for row_index, row in enumerate(df.to_dict(orient="records")):
        lat = _parse_float(row.get("latitude"))
        lng = _parse_float(row.get("longitude"))
        within_patna = False
        distance = math.inf
        if lat is not None and lng is not None:
            distance = _haversine_km(PATNA_LAT, PATNA_LNG, lat, lng)
            within_patna = distance <= PATNA_RADIUS_KM
        keyword_hit = _matches_surgery_keyword(
            *(row.get(col) for col in _KEYWORD_COLUMNS)
        )
        if not (within_patna or keyword_hit):
            continue
        facility_id = facilities.loc[row_index, "facility_id"]
        candidates.append((distance, row_index, str(facility_id)))

    candidates.sort(key=lambda t: (t[0], t[1]))
    selected = [fid for _, _, fid in candidates[:cap]]
    return {
        "_meta": {
            "cap": cap,
            "patna_lat": PATNA_LAT,
            "patna_lng": PATNA_LNG,
            "patna_radius_km": PATNA_RADIUS_KM,
            "surgery_keywords": list(SURGERY_KEYWORDS),
            "csv_sha256": csv_sha,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "selected_count": len(selected),
            "candidate_count": len(candidates),
        },
        "facility_ids": selected,
    }


def _write_parquet(table: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(table, preserve_index=False), path)


def main(
    csv_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    demo_only: bool = False,
    limit: int | None = None,
) -> dict[str, object]:
    """Run the normalization pipeline.

    Returns a small summary dict (chunk count, facility count, demo size,
    csv sha) — handy for tests and the CLI banner.
    """
    csv_p = Path(csv_path) if csv_path is not None else DEFAULT_CSV_PATH
    out_p = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    out_p.mkdir(parents=True, exist_ok=True)

    csv_sha = _csv_sha256(csv_p)
    df = _read_csv(csv_p, limit=limit)
    indexed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    facilities = _build_facilities_index(df)
    chunks = _build_chunks(df, indexed_at=indexed_at)
    demo = _build_demo_subset(df, facilities, csv_sha)

    if demo_only:
        # When ``--demo-only`` is requested we still write the full chunks
        # parquet for the demo subset only, and the index limited to those
        # ids.  Useful for spinning up Vector Search against ~200 rows.
        keep_ids = set(demo["facility_ids"])  # type: ignore[arg-type]
        chunks = chunks[chunks["facility_id"].isin(keep_ids)].reset_index(drop=True)
        facilities = facilities[facilities["facility_id"].isin(keep_ids)].reset_index(drop=True)

    chunks_path = out_p / "chunks.parquet"
    facilities_path = out_p / "facilities_index.parquet"
    demo_path = out_p / "demo_subset.json"

    _write_parquet(chunks, chunks_path)
    _write_parquet(facilities, facilities_path)
    demo_path.write_text(json.dumps(demo, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "csv_path": str(csv_p),
        "csv_sha256": csv_sha,
        "chunk_count": int(len(chunks)),
        "facility_count": int(len(facilities)),
        "demo_subset_count": len(demo["facility_ids"]),  # type: ignore[arg-type]
        "chunks_path": str(chunks_path),
        "facilities_path": str(facilities_path),
        "demo_path": str(demo_path),
    }
    print(
        "[normalize] csv_sha={sha} chunks={c} facilities={f} demo={d}".format(
            sha=csv_sha[:12],
            c=summary["chunk_count"],
            f=summary["facility_count"],
            d=summary["demo_subset_count"],
        )
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--csv", type=str, default=None, help="Path to the VF CSV (default: repo CSV).")
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Where parquet/json outputs land (default: <repo>/tables).",
    )
    p.add_argument(
        "--demo-only",
        action="store_true",
        help="Restrict parquet output to the demo allow-list.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Read only the first N rows from the CSV (smoke testing).",
    )
    return p


def _cli(argv: Iterable[str] | None = None) -> None:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    main(
        csv_path=args.csv,
        output_dir=args.output_dir,
        demo_only=args.demo_only,
        limit=args.limit,
    )


if __name__ == "__main__":
    _cli()
