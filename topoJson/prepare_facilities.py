"""
Adapter: hackathon CSV + parquet trust scores → xlsx for desert_score_model.py.

Reads the raw VF_Hackathon_Dataset CSV, joins computed trust scores from the
pipeline's facility_audits.parquet, and writes an xlsx with the column names
desert_score_model.py expects.
"""
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent

CSV_PATH = next(REPO.glob("VF_Hackathon_Dataset_India_Large*"), None)
PARQUET_PATH = REPO / "tables" / "facility_audits.parquet"
OUT_PATH = Path(__file__).resolve().parent / "facilities_prepared.xlsx"


def score_to_trust_label(score: float | None) -> str:
    if score is None or pd.isna(score):
        return "silent"
    if score >= 80:
        return "supports"
    if score >= 50:
        return "unclear"
    return "contradicts"


def main() -> None:
    if CSV_PATH is None:
        print("ERROR: VF_Hackathon_Dataset CSV not found in repo root", file=sys.stderr)
        sys.exit(1)

    print(f"Reading facilities CSV: {CSV_PATH.name}")
    df = pd.read_csv(CSV_PATH, low_memory=False)
    df = df.rename(columns={"latitude": "lat", "longitude": "lon"})

    if PARQUET_PATH.exists():
        print(f"Joining trust scores from {PARQUET_PATH.name} ({len(df)} facilities)")
        audits = pd.read_parquet(PARQUET_PATH)

        def max_score(ts_json: str) -> float | None:
            ts = json.loads(ts_json)
            if not ts:
                return None
            scores = [v.get("score", 0) for v in ts.values()]
            return max(scores) if scores else None

        def dominant_contradiction(ts_json: str) -> str:
            ts = json.loads(ts_json)
            for v in ts.values():
                for c in v.get("contradictions", []):
                    return c.get("contradiction_type", "")
            return ""

        audits["_max_score"] = audits["trust_scores_json"].apply(max_score)
        audits["_contradiction"] = audits["trust_scores_json"].apply(dominant_contradiction)

        df = df.merge(
            audits[["name", "_max_score", "_contradiction"]],
            on="name",
            how="left",
        )
        df["trustScore"] = df["_max_score"].apply(score_to_trust_label)
        df["contradictionType"] = df["_contradiction"].fillna("")
        df = df.drop(columns=["_max_score", "_contradiction"])
        matched = (df["trustScore"] != "silent").sum()
        print(f"  Matched {matched} facilities with pipeline trust scores")
    else:
        print("No parquet found — defaulting all trust scores to 'silent'")
        df["trustScore"] = "silent"
        df["contradictionType"] = ""

    # Sanitize strings — openpyxl rejects control characters
    import re
    _ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).apply(lambda s: _ILLEGAL.sub("", s))

    print(f"Writing {len(df)} rows to {OUT_PATH.name}")
    df.to_excel(OUT_PATH, index=False)
    print("Done.")


if __name__ == "__main__":
    main()
