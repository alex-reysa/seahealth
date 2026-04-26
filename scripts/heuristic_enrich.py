"""Heuristic capability enrichment over the full 10k corpus.

Scans each facility's chunks for capability keywords and emits rows in the
canonical capabilities.parquet shape (facility_id, capability_type, claimed,
source_doc_id, extractor_model, extracted_at, evidence_refs_json) so the
existing build_audits.py pipeline can fold them into facility_audits.parquet.

Augments — does not replace — the LLM-extracted rows already in
capabilities.parquet. Existing rows take precedence on conflict.

extractor_model is set to ``seahealth-heuristic-v1`` so the data lineage is
honest: these claims were derived from name + chunk-text keyword matching,
not from an LLM.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pyarrow as pa


REPO = Path(__file__).resolve().parent.parent
TABLES = REPO / "tables"

KEYWORDS: dict[str, tuple[str, ...]] = {
    "ONCOLOGY": ("cancer", "oncology", "tata memorial", "chemo", "tumor", "tumour"),
    "MATERNAL": ("maternity", "matru", "prasuti", "obstetric", "gynec", "antenatal", "delivery", "labor ward", "labour ward"),
    "NEONATAL": ("neonatal", "newborn", "nicu", "shishu", "sishu", "paediatric", "pediatric", "child's", "children's", "infant"),
    "ICU": ("icu", "intensive care", "critical care"),
    "TRAUMA": ("trauma centre", "trauma center", "accident & emergency"),
    "DIALYSIS": ("dialysis", "kidney", "renal", "nephro"),
    "LAB": ("pathology lab", "diagnostic lab", "laboratory", "blood test"),
    "RADIOLOGY": ("radiology", "imaging", "x-ray", "xray", "mri", "sonography", "ultrasound", "ct scan"),
    "PHARMACY": ("pharmacy", "medical store", "chemist"),
    "EMERGENCY_24_7": ("24x7", "24 hours", "24-hour", "emergency 24"),
    "SURGERY_GENERAL": ("surgery", "surgical", "operating theatre", "operation theater", " ot ", "anesthesia", "anaesthesia"),
    "SURGERY_APPENDECTOMY": ("appendectomy", "appendicitis", "appendix surgery"),
}

TYPE_BLOCK: dict[str, set[str]] = {
    # facilityTypeId -> set of capabilities to suppress (keep the matcher honest)
    "pharmacy": {"ICU", "TRAUMA", "DIALYSIS", "RADIOLOGY", "ONCOLOGY", "MATERNAL", "NEONATAL", "SURGERY_GENERAL", "SURGERY_APPENDECTOMY"},
    "dentist": {"ICU", "TRAUMA", "DIALYSIS", "ONCOLOGY", "MATERNAL", "NEONATAL", "SURGERY_APPENDECTOMY"},
}


def find_evidence(text: str, keyword: str, window: int = 100) -> tuple[int, int, str] | None:
    """Return (span_start, span_end, snippet) for the first kw hit in text."""
    lower = text.lower()
    idx = lower.find(keyword.lower())
    if idx < 0:
        return None
    start = max(0, idx - 30)
    end = min(len(text), idx + len(keyword) + window)
    snippet = text[start:end].strip()
    return idx, idx + len(keyword), snippet


def main() -> None:
    chunks = pq.read_table(TABLES / "chunks.parquet").to_pandas()
    index = pq.read_table(TABLES / "facilities_index.parquet").to_pandas()
    fid_to_type = dict(zip(index["facility_id"].astype(str), index["facilityTypeId"].astype(str), strict=True))
    fid_to_name = dict(zip(index["facility_id"].astype(str), index["name"].astype(str), strict=True))

    existing_path = TABLES / "capabilities.parquet"
    existing_keys: set[tuple[str, str]] = set()
    existing_rows: list[dict] = []
    if existing_path.exists():
        existing = pq.read_table(existing_path).to_pandas()
        existing_rows = existing.to_dict("records")
        for r in existing_rows:
            existing_keys.add((str(r["facility_id"]), str(r["capability_type"])))

    now = datetime.now(UTC).isoformat()
    new_rows: list[dict] = []
    facilities_touched: set[str] = set()
    by_facility = chunks.groupby("facility_id", sort=False)

    for fid, group in by_facility:
        fid_s = str(fid)
        ftype = fid_to_type.get(fid_s, "").lower()
        blocked = TYPE_BLOCK.get(ftype, set())
        # Concatenate all chunk text, keep per-chunk metadata for evidence_refs
        chunk_records = group.to_dict("records")
        full_text = " \n ".join(str(r.get("text", "")) for r in chunk_records)
        full_text_lower = full_text.lower()
        for cap, kws in KEYWORDS.items():
            if cap in blocked:
                continue
            if (fid_s, cap) in existing_keys:
                continue
            # Find first hit anywhere
            hit_kw = None
            for kw in kws:
                if kw in full_text_lower:
                    hit_kw = kw
                    break
            if not hit_kw:
                continue
            # Locate the chunk that carries the hit so evidence_ref is precise
            evidence_refs = []
            for chunk in chunk_records:
                text = str(chunk.get("text", ""))
                ev = find_evidence(text, hit_kw)
                if ev is None:
                    continue
                start, end, snippet = ev
                evidence_refs.append({
                    "source_doc_id": str(chunk.get("source_doc_id") or fid_s),
                    "facility_id": fid_s,
                    "chunk_id": str(chunk.get("chunk_id") or ""),
                    "row_id": None,
                    "span": [start, end],
                    "snippet": snippet,
                    "source_type": str(chunk.get("source_type") or "facility_note"),
                    "source_observed_at": None,
                    "retrieved_at": now,
                })
                break  # one evidence ref per claim is enough for the demo
            if not evidence_refs:
                continue
            new_rows.append({
                "facility_id": fid_s,
                "capability_type": cap,
                "claimed": True,
                "source_doc_id": evidence_refs[0]["source_doc_id"],
                "extractor_model": "seahealth-heuristic-v1",
                "extracted_at": now,
                "evidence_refs_json": json.dumps(evidence_refs),
            })
            facilities_touched.add(fid_s)
            existing_keys.add((fid_s, cap))

    print(f"[enrich] new heuristic claims: {len(new_rows)}")
    print(f"[enrich] facilities now covered: existing {len({r['facility_id'] for r in existing_rows})} -> total {len({r['facility_id'] for r in existing_rows} | facilities_touched)}")

    merged = existing_rows + new_rows
    table = pa.Table.from_pylist(merged)
    pq.write_table(table, existing_path)
    print(f"[enrich] wrote {len(merged)} rows to {existing_path}")


if __name__ == "__main__":
    main()
