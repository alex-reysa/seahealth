"""Tests for ``seahealth.pipelines.normalize``.

Uses a tiny inline CSV fixture written to ``tmp_path`` so the tests do not
depend on the 10k-row VF dump.  Five fixture rows cover: a Patna-area
surgery facility, a Patna-area dental clinic (no surgery keyword), a
Mumbai surgery facility (keyword match, far from Patna), a row with empty
equipment, a row with weird unicode in the name, and an out-of-Patna
non-surgery facility used to assert exclusion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from seahealth.pipelines import normalize

# ---------------------------------------------------------------------------
# Fixture CSV
# ---------------------------------------------------------------------------


CSV_HEADER = (
    "name,phone_numbers,officialPhone,email,websites,officialWebsite,yearEstablished,"
    "facebookLink,twitterLink,linkedinLink,instagramLink,"
    "address_line1,address_line2,address_line3,address_city,address_stateOrRegion,address_zipOrPostcode,"
    "address_country,address_countryCode,facilityTypeId,operatorTypeId,affiliationTypeIds,"
    "description,numberDoctors,capacity,specialties,procedure,equipment,capability,"
    "recency_of_page_update,distinct_social_media_presence_count,affiliated_staff_presence,"
    "custom_logo_presence,number_of_facts_about_the_organization,post_metrics_most_recent_social_media_post_date,"
    "post_metrics_post_count,engagement_metrics_n_followers,engagement_metrics_n_likes,"
    "engagement_metrics_n_engagements,latitude,longitude"
)


def _row(
    *,
    name: str,
    city: str,
    state: str,
    pin: str,
    description: str,
    specialties: str,
    procedure: str,
    equipment: str,
    capability: str,
    lat: str,
    lng: str,
    facility_type: str = "hospital",
    number_doctors: str = "5",
    capacity: str = "20",
    recency: str = "0_to_3_months",
) -> str:
    """Return a single fixture CSV row.

    Free-text columns are wrapped in double quotes; embedded double quotes
    are doubled per RFC 4180.
    """

    def q(s: str) -> str:
        return '"' + s.replace('"', '""') + '"'

    cells = [
        q(name),                        # name
        q('["+910000000000"]'),        # phone_numbers
        "+910000000000",                # officialPhone
        "test@example.com",             # email
        q('["https://example.com"]'), # websites
        "https://example.com",          # officialWebsite
        "null",                         # yearEstablished
        "null",                         # facebookLink
        "null",                         # twitterLink
        "null",                         # linkedinLink
        "null",                         # instagramLink
        q("Test Address Line 1"),     # address_line1
        "null",                         # address_line2
        "null",                         # address_line3
        q(city),                        # address_city
        q(state),                       # address_stateOrRegion
        pin,                            # address_zipOrPostcode
        "India",                        # address_country
        "IN",                           # address_countryCode
        facility_type,                  # facilityTypeId
        "private",                      # operatorTypeId
        "null",                         # affiliationTypeIds
        q(description),                 # description
        number_doctors,                 # numberDoctors
        capacity,                       # capacity
        q(specialties),                 # specialties
        q(procedure),                   # procedure
        q(equipment),                   # equipment
        q(capability),                  # capability
        recency,                        # recency_of_page_update
        "1",                            # distinct_social_media_presence_count
        "TRUE",                         # affiliated_staff_presence
        "TRUE",                         # custom_logo_presence
        "1",                            # number_of_facts_about_the_organization
        "null",                         # post_metrics_most_recent_social_media_post_date
        "null",                         # post_metrics_post_count
        "null",                         # engagement_metrics_n_followers
        "null",                         # engagement_metrics_n_likes
        "null",                         # engagement_metrics_n_engagements
        lat,                            # latitude
        lng,                            # longitude
    ]
    return ",".join(cells)


@pytest.fixture()
def fixture_csv(tmp_path: Path) -> Path:
    rows = [
        # Row 0: Patna area + surgery keyword -> demo include (both criteria).
        _row(
            name="Patna General Surgery Hospital",
            city="Patna",
            state="Bihar",
            pin="800001",
            description=(
                "A general surgery hospital offering appendectomy and laparoscopic procedures."
            ),
            specialties='["generalSurgery","gastroenterology"]',
            procedure='["Performs appendectomy","Performs laparoscopic surgery"]',
            equipment='["Anesthesia machine","Operating table","Laparoscope"]',
            capability='["General surgery available 24/7","Operating theatre staffed"]',
            lat="25.62",
            lng="85.15",
        ),
        # Row 1: Patna area, dental clinic -> demo include (distance only).
        _row(
            name="Patna Smiles Dental Clinic",
            city="Patna",
            state="Bihar",
            pin="800002",
            description="Dental clinic offering routine cleanings and orthodontia.",
            specialties='["dentistry","orthodontics"]',
            procedure='["Routine cleanings","Braces fitting"]',
            equipment='["Dental chair","X-ray machine"]',
            capability='["General dentistry"]',
            lat="25.61",
            lng="85.14",
            facility_type="dentist",
        ),
        # Row 2: Mumbai (far) + surgery keyword -> demo include (keyword only).
        _row(
            name="Mumbai Advanced Surgical Center",
            city="Mumbai",
            state="Maharashtra",
            pin="400001",
            description="Tertiary hospital with advanced general surgery and trauma services.",
            specialties='["generalSurgery","trauma"]',
            procedure='["Performs appendectomy","Trauma surgery"]',
            equipment='["Anesthesia machine","CT scanner"]',
            capability='["Operating theatre 24/7"]',
            lat="19.0760",
            lng="72.8777",
        ),
        # Row 3: Empty equipment -> chunk should render "(none listed)".
        # Far from Patna and no surgery keyword -> should NOT be in demo.
        _row(
            name="Chennai Routine Outpatient Clinic",
            city="Chennai",
            state="Tamil Nadu",
            pin="600001",
            description="Outpatient checkups and vaccinations.",
            specialties='["familyMedicine"]',
            procedure="[]",
            equipment="[]",
            capability="[]",
            lat="13.0827",
            lng="80.2707",
            facility_type="clinic",
        ),
        # Row 4: Unicode name + Patna proximity -> include via distance.
        _row(
            name="Pātnā Āyurveda Centre — श्री",
            city="Patna",
            state="Bihar",
            pin="800003",
            description="Traditional medicine centre, no surgery offered.",
            specialties='["ayurveda"]',
            procedure='["Panchakarma"]',
            equipment='["Massage table"]',
            capability='["Ayurvedic consultations"]',
            lat="25.60",
            lng="85.13",
            facility_type="clinic",
        ),
    ]
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return csv_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _read_parquet(path: Path) -> pd.DataFrame:
    return pq.read_table(path).to_pandas()


def test_pipeline_writes_chunks_facilities_and_demo(
    fixture_csv: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "tables"
    summary = normalize.main(csv_path=fixture_csv, output_dir=output_dir)

    chunks = _read_parquet(output_dir / "chunks.parquet")
    facilities = _read_parquet(output_dir / "facilities_index.parquet")
    demo = json.loads((output_dir / "demo_subset.json").read_text(encoding="utf-8"))

    # 5 rows × 4 source types = 20 chunks.
    assert len(chunks) == 20
    assert summary["chunk_count"] == 20
    assert summary["facility_count"] == 5

    # Stable facility_id pattern: source-field hash + readable slug, not row index.
    facility_ids = facilities["facility_id"].tolist()
    for fid in facility_ids:
        prefix, digest, slug = fid.split("_", 2)
        assert prefix == "vf"
        assert len(digest) == 12
        assert slug

    # CSV sha is included in the demo metadata.
    assert demo["_meta"]["csv_sha256"] == summary["csv_sha256"]
    assert len(demo["_meta"]["csv_sha256"]) == 64
    assert not list(output_dir.glob("*.tmp"))


def test_chunk_text_prefixes_and_ordering(fixture_csv: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "tables"
    normalize.main(csv_path=fixture_csv, output_dir=output_dir)
    chunks = _read_parquet(output_dir / "chunks.parquet")

    expected = {
        "facility_note": "[FACILITY NOTE]",
        "staff_roster": "[STAFF ROSTER]",
        "equipment_inventory": "[EQUIPMENT INVENTORY]",
        "volume_report": "[VOLUME REPORT]",
    }
    for source_type, prefix in expected.items():
        subset = chunks[chunks["source_type"] == source_type]
        assert len(subset) == 5
        for text in subset["text"]:
            assert text.startswith(prefix), text[:40]

    # span offsets are Python character offsets, not UTF-8 byte offsets.
    for _, row in chunks.iterrows():
        assert row["span_start"] == 0
        assert row["span_end"] == len(row["text"])

    unicode_chunk = chunks[
        (chunks["row_index"] == 4) & (chunks["source_type"] == "facility_note")
    ].iloc[0]
    assert len(unicode_chunk["text"].encode("utf-8")) > unicode_chunk["span_end"]


def test_empty_equipment_renders_none_listed(fixture_csv: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "tables"
    normalize.main(csv_path=fixture_csv, output_dir=output_dir)
    chunks = _read_parquet(output_dir / "chunks.parquet")

    # Row 3 (Chennai) has empty equipment, procedure, capability lists.
    chennai_equipment = chunks[
        (chunks["row_index"] == 3) & (chunks["source_type"] == "equipment_inventory")
    ].iloc[0]
    assert "(none listed)" in chennai_equipment["text"]

    chennai_volume = chunks[
        (chunks["row_index"] == 3) & (chunks["source_type"] == "volume_report")
    ].iloc[0]
    assert "Claimed capabilities: (none listed)" in chennai_volume["text"]
    assert "Claimed procedures: (none listed)" in chennai_volume["text"]


def test_unicode_survives_round_trip(fixture_csv: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "tables"
    normalize.main(csv_path=fixture_csv, output_dir=output_dir)

    facilities = _read_parquet(output_dir / "facilities_index.parquet")
    chunks = _read_parquet(output_dir / "chunks.parquet")

    row4_name = facilities[facilities["row_index"] == 4].iloc[0]["name"]
    assert "Pātnā" in row4_name
    assert "श्री" in row4_name

    facility_note = chunks[
        (chunks["row_index"] == 4) & (chunks["source_type"] == "facility_note")
    ].iloc[0]["text"]
    assert "Pātnā" in facility_note
    assert "श्री" in facility_note


def test_demo_subset_membership(fixture_csv: Path, tmp_path: Path) -> None:
    """Patna surgery + Mumbai surgery + Patna dental + Patna ayurveda all in;
    Chennai outpatient out."""
    output_dir = tmp_path / "tables"
    normalize.main(csv_path=fixture_csv, output_dir=output_dir)
    facilities = _read_parquet(output_dir / "facilities_index.parquet")
    demo = json.loads((output_dir / "demo_subset.json").read_text(encoding="utf-8"))

    by_row = {
        int(row.row_index): row.facility_id for row in facilities.itertuples(index=False)
    }
    selected = set(demo["facility_ids"])

    # Patna surgery hospital -> distance + keyword.
    assert by_row[0] in selected
    # Patna dental clinic -> distance only.
    assert by_row[1] in selected
    # Mumbai surgery -> keyword only (far from Patna).
    assert by_row[2] in selected
    # Patna ayurveda -> distance only.
    assert by_row[4] in selected
    # Chennai outpatient -> NEITHER, must be excluded.
    assert by_row[3] not in selected


def test_facility_ids_are_stable_when_csv_order_changes(
    fixture_csv: Path, tmp_path: Path
) -> None:
    original_dir = tmp_path / "original"
    reordered_dir = tmp_path / "reordered"
    reordered_csv = tmp_path / "reordered.csv"

    df = pd.read_csv(fixture_csv, dtype=str, keep_default_na=False)
    reordered = pd.concat([df.iloc[[2]], df.drop(index=2)], ignore_index=True)
    reordered.to_csv(reordered_csv, index=False)

    normalize.main(csv_path=fixture_csv, output_dir=original_dir)
    normalize.main(csv_path=reordered_csv, output_dir=reordered_dir)

    original = _read_parquet(original_dir / "facilities_index.parquet")
    shuffled = _read_parquet(reordered_dir / "facilities_index.parquet")

    original_ids = dict(zip(original["name"], original["facility_id"], strict=True))
    shuffled_ids = dict(zip(shuffled["name"], shuffled["facility_id"], strict=True))
    assert shuffled_ids == original_ids


def test_chunk_text_is_trimmed_utf8_and_spans_use_python_chars() -> None:
    text = normalize._normalize_chunk_text(" \x00Cafe\u0301\n")
    assert text == "Café"
    assert normalize._python_char_span(text) == (0, 4)
    assert len(text.encode("utf-8")) == 5


def test_demo_subset_surgery_keyword_boundary_variants() -> None:
    assert normalize._matches_surgery_keyword("dedicated operation theatre")
    assert normalize._matches_surgery_keyword("dedicated operating theater")
    assert normalize._matches_surgery_keyword("operative procedures suite")


def test_facility_index_dtypes_and_pin_filtering(
    fixture_csv: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "tables"
    normalize.main(csv_path=fixture_csv, output_dir=output_dir)
    facilities = _read_parquet(output_dir / "facilities_index.parquet")

    # PIN codes are all 6-digit so all should pass through.
    assert facilities["pin_code"].notna().all()
    # latitude/longitude coerced to float.
    assert facilities["latitude"].dtype.kind == "f"
    assert facilities["longitude"].dtype.kind == "f"
    # numberDoctors / capacity nullable Int64.
    assert str(facilities["numberDoctors"].dtype) == "Int64"
    assert str(facilities["capacity"].dtype) == "Int64"


def test_demo_only_filters_outputs(fixture_csv: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "tables"
    normalize.main(csv_path=fixture_csv, output_dir=output_dir, demo_only=True)
    chunks = _read_parquet(output_dir / "chunks.parquet")
    facilities = _read_parquet(output_dir / "facilities_index.parquet")
    demo = json.loads((output_dir / "demo_subset.json").read_text(encoding="utf-8"))

    selected = set(demo["facility_ids"])
    assert set(facilities["facility_id"]) == selected
    assert set(chunks["facility_id"]) <= selected
    # Each retained facility still emits four chunks.
    assert len(chunks) == 4 * len(selected)
