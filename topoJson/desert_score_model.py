"""
desert_score_model.py
=====================

AXON Health Intelligence  Layer 2 (Population Need + Coverage) pipeline.

Computes a per-district Desert Score combining NFHS-5 neonatal need indicators
with verified facility coverage from the upstream Trust Score agent, and
exports a TopoJSON consumed by the frontend map.

Pipeline
--------
1. Load facility xlsx (with pre-computed Trust Scores from the agent layer),
   NFHS-5 district indicators CSV, and Districts.geojson boundaries.
2. Filter facilities to neonatal-relevant rows (specialty/capability match).
3. For each district representative point, find all neonatal facilities
   within radius R using a haversine BallTree; sum their Trust Weights and
   normalize against COVERAGE_SATURATION.
4. Compute Need Index = NMR * (1 - SBA/100).
5. Compute Desert Score = Need Index / (Coverage Quality + EPSILON).
6. Quantile-bin into risk tiers; aggregate dominant contradiction type per
   district from facilities inside the radius.
7. Repeat 3-6 for each radius in {30, 60, 120} km, embed all variants as
   suffixed properties on each district feature, and export a single
   TopoJSON ready for the frontend.

Run as a script:
    python desert_score_model.py \\
        --facilities VF_Hackathon_Dataset_India_Large.xlsx \\
        --nfhs nfhs5_districts.csv \\
        --districts Districts.geojson \\
        --out india_desert_layer.topojson

Or import build_multi_radius_topojson() into a Databricks notebook and wrap
with mlflow.start_run() for tracing.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

try:
    import geopandas as gpd
except ImportError:  # let scoring-path callers import without geopandas
    gpd = None  # type: ignore[assignment]

try:
    import topojson as tp
except ImportError:  # surfaced at export time with a clearer message
    tp = None

logger = logging.getLogger("desert_score")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0088
EPSILON = 0.01

TRUST_WEIGHTS: dict[str, float] = {
    "supports": 1.0,
    "unclear": 0.5,
    "contradicts": 0.1,
    "silent": 0.05,
}

# Saturation cap for Coverage Quality normalization. The sum of Trust Weights
# of neonatal-relevant facilities within the radius is divided by this value
# and clipped to 1.0. 10.0 ~= "ten fully verified neonatal facilities within R
# is full coverage". Tune against domain prior; document any change.
COVERAGE_SATURATION = 10.0

# Lowercased substring tokens. A facility is neonatal-relevant if any token
# appears in its concatenated specialty + capability text after stripping
# non-alphanumerics.
NEONATAL_TOKENS: tuple[str, ...] = (
    "nicu",
    "picu",
    "neonatal",
    "neonatology",
    "neonatologyperinatalmedicine",
    "pediatriccriticalcaremedicine",
    "pediatrics",
    "maternity",
    "obstetrics",
    "obstetricsandmaternitycare",
    "maternalfetalmedicineorperinatology",
)

DEFAULT_RADII_KM: tuple[int, ...] = (30, 60, 120)

# Quantile lower bounds (inclusive) for each risk tier on Desert Score.
RISK_TIER_QUANTILES = {
    "critical": 0.80,
    "high":     0.60,
    "moderate": 0.30,
    # "low" is everything below 0.30
}

CHOROPLETH_HEX = {
    "critical": "#050505",
    "high":     "#0d1a0d",
    "moderate": "#1a2e0a",
    "low":      "#2a4a1a",
    "missing":  "#4a4a4a",
}

CHOROPLETH_OPACITY = {
    "critical": 0.75,
    "high":     0.55,
    "moderate": 0.55,
    "low":      0.55,
    "missing":  0.40,
}

# Expected column names. Override via load_*() kwargs if your dataset uses
# different headers. These are best-guess defaults; verify against actuals.
FACILITY_COLS = {
    "lat": "lat",
    "lon": "lon",
    "trust_score": "trustScore",
    "specialties": "specialties",
    "capability": "capability",
    "facility_type_id": "facilityTypeId",
    "contradiction_type": "contradictionType",  # optional, may be absent
}

# NFHS-5 districts CSV ships in long format (one row per indicator). The
# pivot in load_nfhs() turns this into wide format; everything below assumes
# wide. Internal indicator key -> exact NFHS Indicator string. Indicators
# missing from the source file come through as NaN and the proxy NeedIndex
# (compute_need_index_proxy) takes over downstream.
NFHS_LONG_KEYS = ("State", "District", "DISTRICT", "ST_CEN_CD", "DT_CEN_CD")

NFHS_INDICATORS: dict[str, str] = {
    "nmr": "Neonatal mortality rate (per 1000 live births)",
    "sba": "Births attended by skilled health personnel (%)",
    "institutional_births": "Institutional births (%)",
    "anc4_plus": "Mothers who had at least 4 antenatal care visits (%)",
}

NFHS_COLS = {
    "district":      "DISTRICT",
    "state":         "State",
    "state_code":    "ST_CEN_CD",
    "district_code": "DT_CEN_CD",
    "births":        None,  # NFHS-5 districts CSV does not include birth volume
}

DISTRICTS_COLS = {
    "district":      "DISTRICT",
    "state":         "ST_NM",
    "display":       "Dist_name",
    "state_code":    "ST_CEN_CD",
    "district_code": "DT_CEN_CD",
}

# Common spelling/standardization fixes. Extend after the validation report
# logs unmatched districts on first run.
DISTRICT_NAME_FIXES: dict[str, str] = {
    "ahmadabad": "ahmedabad",
    "allahabad": "prayagraj",
    "bangalore rural": "bengaluru rural",
    "bangalore urban": "bengaluru urban",
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "gurgaon": "gurugram",
    "kanpur dehat": "kanpur rural",
    "leh ladakh": "leh",
    "mahbubnagar": "mahabubnagar",
    "pondicherry": "puducherry",
    "rangareddy": "ranga reddy",
    "saraikela kharsawan": "seraikela kharsawan",
    "ysr": "ysr kadapa",
    "y s r": "ysr kadapa",
}


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_MULTISPACE = re.compile(r"\s+")


def normalize_district(name: object) -> str:
    """Lowercase, strip diacritics, collapse spaces, apply fix table."""
    if pd.isna(name):
        return ""
    s = str(name).lower().strip()
    s = _NON_ALNUM.sub(" ", s)
    s = _MULTISPACE.sub(" ", s).strip()
    return DISTRICT_NAME_FIXES.get(s, s)


def normalize_state(name: object) -> str:
    if pd.isna(name):
        return ""
    s = str(name).lower().strip()
    s = _NON_ALNUM.sub(" ", s)
    s = _MULTISPACE.sub(" ", s).strip()
    return s


def _flatten_text(value: object) -> str:
    """Coerce free-text / list-like fields to a single lowercase blob."""
    if pd.isna(value):
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(x) for x in value).lower()
    return str(value).lower()


def is_neonatal_relevant(specialties: object, capability: object) -> bool:
    blob = _flatten_text(specialties) + " " + _flatten_text(capability)
    blob = re.sub(r"[^a-z0-9]", "", blob)
    return any(tok in blob for tok in NEONATAL_TOKENS)


# ---------------------------------------------------------------------------
# NFHS pivot + proxy NeedIndex
# ---------------------------------------------------------------------------

def pivot_nfhs_long_to_wide(df_long: pd.DataFrame) -> pd.DataFrame:
    """Pivot the NFHS long-format CSV (one row per indicator) to wide format.

    Uses NFHS 5 with NFHS 4 as fallback. Rows missing both Census codes
    (state/national aggregates) are dropped before pivoting so the result
    is one row per (ST_CEN_CD, DT_CEN_CD).
    """
    df = df_long.copy()
    df.columns = [c.strip() for c in df.columns]
    needed = list(NFHS_LONG_KEYS) + ["Indicator", "NFHS 5"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(
            f"NFHS CSV missing expected long-format columns: {missing}. "
            f"Available: {list(df.columns)[:30]}"
        )

    df["ST_CEN_CD"] = pd.to_numeric(df["ST_CEN_CD"], errors="coerce")
    df["DT_CEN_CD"] = pd.to_numeric(df["DT_CEN_CD"], errors="coerce")
    n0 = len(df)
    df = df.dropna(subset=["ST_CEN_CD", "DT_CEN_CD"])
    if len(df) < n0:
        logger.info("nfhs pivot: dropped %d non-district rows", n0 - len(df))

    primary = pd.to_numeric(df["NFHS 5"], errors="coerce")
    if "NFHS 4" in df.columns:
        fallback = pd.to_numeric(df["NFHS 4"], errors="coerce")
        df["_value"] = primary.fillna(fallback)
    else:
        df["_value"] = primary

    wide = (
        df.pivot_table(
            index=list(NFHS_LONG_KEYS),
            columns="Indicator",
            values="_value",
            aggfunc="first",
        )
        .reset_index()
    )
    wide.columns.name = None
    return wide


def compute_need_index_proxy(
    sba: pd.Series,
    institutional_births: pd.Series,
    anc4_plus: pd.Series,
) -> pd.Series:
    """NeedIndex proxy when district-level NMR is unavailable.

    Compounds three NFHS-5 indicators that are leading neonatal-mortality
    risk factors: lack of skilled birth attendance, non-institutional
    births, and missed antenatal care. Output is on a 0-100 scale,
    weighted toward SBA (the strongest direct predictor) and roughly
    comparable in magnitude to typical Indian district NMR (~10-50).
    """
    sba_gap  = (100.0 - sba.astype(float).clip(0, 100)) / 100.0
    inst_gap = (100.0 - institutional_births.astype(float).clip(0, 100)) / 100.0
    anc_gap  = (100.0 - anc4_plus.astype(float).clip(0, 100)) / 100.0
    return 100.0 * (0.5 * sba_gap + 0.3 * inst_gap + 0.2 * anc_gap)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_facilities(path: str | Path, cols: dict[str, str] | None = None) -> pd.DataFrame:
    cols = {**FACILITY_COLS, **(cols or {})}
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]

    missing = [v for k, v in cols.items() if k != "contradiction_type" and v not in df.columns]
    if missing:
        raise ValueError(
            f"Facility file is missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}. "
            f"Pass a cols={{...}} mapping to load_facilities() to remap."
        )

    n0 = len(df)
    df = df.dropna(subset=[cols["lat"], cols["lon"]])
    df = df[
        df[cols["lat"]].between(6, 38) & df[cols["lon"]].between(68, 98)
    ].copy()

    # Map trust score to weight; unknowns -> silent
    ts = df[cols["trust_score"]].astype(str).str.lower().str.strip()
    unknown = ~ts.isin(TRUST_WEIGHTS)
    if unknown.any():
        logger.warning(
            "facilities: %d rows have unrecognized trustScore values "
            "(mapped to 'silent'): %s",
            int(unknown.sum()),
            sorted(ts[unknown].unique())[:10],
        )
    ts = ts.where(~unknown, "silent")
    df["_trust_score"] = ts
    df["_trust_weight"] = ts.map(TRUST_WEIGHTS).astype(float)

    # Neonatal relevance flag - vectorized: lower, strip non-alphanumeric,
    # match any token. List/tuple cells coerce via str() so substring lookups
    # still work without per-row Python.
    spec_text = df[cols["specialties"]].fillna("").astype(str).str.lower()
    cap_text  = df[cols["capability"]].fillna("").astype(str).str.lower()
    blob = (spec_text + " " + cap_text).str.replace(r"[^a-z0-9]", "", regex=True)
    pattern = "|".join(re.escape(t) for t in NEONATAL_TOKENS)
    df["_is_neonatal"] = blob.str.contains(pattern, regex=True, na=False)

    df["_lat"] = df[cols["lat"]].astype(float)
    df["_lon"] = df[cols["lon"]].astype(float)
    df["_contradiction_type"] = (
        df[cols["contradiction_type"]].astype(str)
        if cols.get("contradiction_type") in df.columns
        else ""
    )

    logger.info(
        "facilities: %d kept / %d original; %d neonatal-relevant",
        len(df), n0, int(df["_is_neonatal"].sum()),
    )
    return df


def load_nfhs(path: str | Path, cols: dict[str, str] | None = None) -> pd.DataFrame:
    """Load NFHS-5 districts CSV. Auto-pivots long format if detected.

    The standard release is one row per (State, District, Indicator). After
    pivoting, NFHS_INDICATORS are coerced to internal `_<key>` columns;
    any indicator absent from the file lands as NaN and the proxy NeedIndex
    fills the gap downstream. Census codes (ST_CEN_CD, DT_CEN_CD) are kept
    as the primary join key against Districts.geojson.
    """
    cols = {**NFHS_COLS, **(cols or {})}
    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip() for c in df.columns]

    if "Indicator" in df.columns:
        df = pivot_nfhs_long_to_wide(df)
        logger.info(
            "nfhs: pivoted long-format CSV -> %d districts, %d cols",
            len(df), len(df.columns),
        )

    needed = [cols["district"], cols["state"], cols["state_code"], cols["district_code"]]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(
            f"NFHS CSV missing key columns after pivot: {missing}. "
            f"Available: {list(df.columns)[:30]}..."
        )

    df["_district_key"]  = df[cols["district"]].apply(normalize_district)
    df["_state_key"]     = df[cols["state"]].apply(normalize_state)
    df["_state_code"]    = pd.to_numeric(df[cols["state_code"]], errors="coerce").astype("Int64")
    df["_district_code"] = pd.to_numeric(df[cols["district_code"]], errors="coerce").astype("Int64")

    for key, indicator_name in NFHS_INDICATORS.items():
        out = f"_{key}"
        if indicator_name in df.columns:
            df[out] = pd.to_numeric(df[indicator_name], errors="coerce")
        else:
            df[out] = np.nan
            logger.info("nfhs: indicator %r not present; %s left NaN", indicator_name, out)

    if cols.get("births") and cols["births"] in df.columns:
        df["_births"] = pd.to_numeric(df[cols["births"]], errors="coerce")
    else:
        df["_births"] = np.nan
    return df


def load_districts(path: str | Path, cols: dict[str, str] | None = None) -> gpd.GeoDataFrame:
    if gpd is None:
        raise ImportError(
            "geopandas is required for load_districts(). "
            "Install with: pip install geopandas (macOS may need `brew install gdal` first)."
        )
    cols = {**DISTRICTS_COLS, **(cols or {})}
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf.set_crs(epsg=4326, inplace=True)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    gdf["_district_key"] = gdf[cols["district"]].apply(normalize_district)
    gdf["_state_key"]    = gdf[cols["state"]].apply(normalize_state)

    if cols.get("state_code") and cols["state_code"] in gdf.columns:
        gdf["_state_code"] = pd.to_numeric(gdf[cols["state_code"]], errors="coerce").astype("Int64")
    else:
        gdf["_state_code"] = pd.array([pd.NA] * len(gdf), dtype="Int64")
    if cols.get("district_code") and cols["district_code"] in gdf.columns:
        gdf["_district_code"] = pd.to_numeric(gdf[cols["district_code"]], errors="coerce").astype("Int64")
    else:
        gdf["_district_code"] = pd.array([pd.NA] * len(gdf), dtype="Int64")

    # representative_point() guarantees a point inside the polygon - robust
    # for irregular / multi-part geometries (coastal, riverine districts).
    pts = gdf.geometry.representative_point()
    gdf["_lat"] = pts.y
    gdf["_lon"] = pts.x
    return gdf


# ---------------------------------------------------------------------------
# Joins & validation
# ---------------------------------------------------------------------------

def join_nfhs_to_districts(
    districts: gpd.GeoDataFrame, nfhs: pd.DataFrame
) -> gpd.GeoDataFrame:
    """Left-join NFHS metrics onto district polygons.

    Primary join is on Census codes (ST_CEN_CD, DT_CEN_CD) which are exact
    integer keys present in both files. Districts that don't match by code
    fall back to normalized (district_name, state_name). Remaining NaN cells
    are imputed with state mean, then national mean.

    Output adds two provenance fields per row:
      nfhs_match_quality: how the row's data was sourced - one of
        'direct'        - matched by Census codes
        'name_fallback' - matched by normalized (district, state) name
        'state_mean'    - no row match; state-mean imputation used
        'national_mean' - state had no data either; national-mean used
      nfhs_imputed: True iff ANY value on this row required imputation
        (i.e. fell back to state or national mean for at least one
        indicator). A direct/name match with complete indicators is False.
    """
    indicator_cols = [f"_{k}" for k in NFHS_INDICATORS]
    value_cols = indicator_cols + ["_births"]

    code_pairs = nfhs.dropna(subset=["_state_code", "_district_code"])[
        ["_state_code", "_district_code"]
    ]
    n_dups = int(code_pairs.duplicated().sum())
    if n_dups:
        logger.warning(
            "nfhs: %d duplicate (state_code, district_code) rows; "
            "groupby-first keeps the first non-null value per indicator",
            n_dups,
        )

    nfhs_by_code = (
        nfhs[["_state_code", "_district_code", *value_cols]]
        .dropna(subset=["_state_code", "_district_code"])
        .groupby(["_state_code", "_district_code"], dropna=False)
        .first()
        .reset_index()
    )
    merged = districts.merge(
        nfhs_by_code,
        on=["_state_code", "_district_code"], how="left",
    )

    match_quality = np.array(["direct"] * len(merged), dtype=object)

    code_unmatched = merged[indicator_cols].isna().all(axis=1).values
    n_code_unmatched = int(code_unmatched.sum())
    if n_code_unmatched:
        nfhs_by_name = (
            nfhs[["_district_key", "_state_key", *value_cols]]
            .groupby(["_district_key", "_state_key"], dropna=False)
            .first()
            .reset_index()
        )
        name_match = districts.loc[code_unmatched, ["_district_key", "_state_key"]].merge(
            nfhs_by_name, on=["_district_key", "_state_key"], how="left",
        )
        for col in value_cols:
            merged.loc[code_unmatched, col] = name_match[col].values
        name_helped = code_unmatched & ~merged[indicator_cols].isna().all(axis=1).values
        match_quality[name_helped] = "name_fallback"
        match_quality[code_unmatched & ~name_helped] = "state_mean"
        logger.info(
            "join: %d code-unmatched, %d resolved by name fallback, %d -> state_mean",
            n_code_unmatched,
            int(name_helped.sum()),
            int((code_unmatched & ~name_helped).sum()),
        )

    # Per-row "any cell imputed" tracker - flips on for state OR national fillna
    imputed_any = np.zeros(len(merged), dtype=bool)

    state_means = nfhs.groupby("_state_key")[value_cols].mean()
    for col in value_cols:
        before = merged[col].isna().values
        fill = merged["_state_key"].map(state_means[col])
        merged[col] = merged[col].fillna(fill)
        after = merged[col].isna().values
        imputed_any |= (before & ~after)

    for col in indicator_cols:
        nat_mean = nfhs[col].mean()
        if pd.isna(nat_mean):
            continue
        before = merged[col].isna().values
        merged[col] = merged[col].fillna(nat_mean)
        after = merged[col].isna().values
        nat_filled = before & ~after
        imputed_any |= nat_filled
        # If a row needed national-mean for any indicator, it's the worst case
        downgrade = nat_filled & np.isin(match_quality, ["direct", "name_fallback", "state_mean"])
        match_quality[downgrade] = "national_mean"

    n_state = int(np.sum(match_quality == "state_mean"))
    n_national = int(np.sum(match_quality == "national_mean"))
    if n_state or n_national:
        logger.warning(
            "join: %d districts using state-mean, %d using national-mean (out of %d)",
            n_state, n_national, len(merged),
        )

    merged["nfhs_match_quality"] = match_quality
    merged["nfhs_imputed"] = imputed_any | np.isin(
        match_quality, ["state_mean", "national_mean"]
    )

    return merged


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_need_index(nmr: pd.Series, sba: pd.Series) -> pd.Series:
    """Default per-spec formula. NMR per 1000 live births, SBA in percent."""
    return nmr.astype(float) * (1.0 - sba.astype(float) / 100.0)


def compute_need_index_volume_weighted(
    nmr: pd.Series, sba: pd.Series, births: pd.Series
) -> pd.Series:
    """Variant that surfaces high-rate AND high-volume districts.

    Falls back to the default formula where birth count is missing.
    """
    base = compute_need_index(nmr, sba)
    log_births = np.log1p((births.fillna(0).astype(float)) / 1000.0)
    # Where births is missing we keep the base index unchanged.
    return np.where(births.notna(), base * log_births, base)


def compute_coverage_quality(
    district_lats: np.ndarray,
    district_lons: np.ndarray,
    facility_lats: np.ndarray,
    facility_lons: np.ndarray,
    facility_weights: np.ndarray,
    facility_trust_score: np.ndarray,
    facility_contradiction_type: np.ndarray,
    radius_km: float,
    saturation: float = COVERAGE_SATURATION,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Haversine BallTree query. Returns (coverage_quality, raw_sum,
    verified_count, dominant_contradiction_type) aligned to districts.

    verified_count = number of facilities within radius whose trust is
    'supports'. raw_sum = unsaturated weighted sum. Coverage quality =
    min(raw_sum / saturation, 1.0).
    """
    if facility_lats.size == 0:
        n = district_lats.size
        return (
            np.zeros(n),
            np.zeros(n),
            np.zeros(n, dtype=int),
            [""] * n,
        )

    fac_rad = np.deg2rad(np.column_stack([facility_lats, facility_lons]))
    dist_rad = np.deg2rad(np.column_stack([district_lats, district_lons]))
    tree = BallTree(fac_rad, metric="haversine")
    radius = radius_km / EARTH_RADIUS_KM

    idx_lists = tree.query_radius(dist_rad, r=radius)

    raw_sum = np.zeros(len(district_lats))
    verified_count = np.zeros(len(district_lats), dtype=int)
    dominant_contradiction: list[str] = []

    for i, idx in enumerate(idx_lists):
        if idx.size == 0:
            dominant_contradiction.append("")
            continue
        raw_sum[i] = facility_weights[idx].sum()
        verified_count[i] = int(np.sum(facility_trust_score[idx] == "supports"))
        # Most common contradiction type among contradicts/unclear facilities
        mask = np.isin(facility_trust_score[idx], ["contradicts", "unclear"])
        if mask.any():
            types = [
                t for t in facility_contradiction_type[idx][mask]
                if t and t.lower() != "nan" and t.strip()
            ]
            dominant_contradiction.append(
                Counter(types).most_common(1)[0][0] if types else ""
            )
        else:
            dominant_contradiction.append("")

    coverage_quality = np.minimum(raw_sum / saturation, 1.0)
    return coverage_quality, raw_sum, verified_count, dominant_contradiction


def compute_desert_score(
    need_index: np.ndarray | pd.Series, coverage_quality: np.ndarray | pd.Series
) -> np.ndarray:
    return np.asarray(need_index) / (np.asarray(coverage_quality) + EPSILON)


def assign_risk_tier(desert_score: np.ndarray) -> np.ndarray:
    """Quantile-bin desert scores. NaN -> 'low' as a safe default."""
    s = pd.Series(desert_score)
    if s.dropna().empty:
        return np.array(["low"] * len(s))
    q = s.quantile(list(RISK_TIER_QUANTILES.values()))
    crit = q[RISK_TIER_QUANTILES["critical"]]
    high = q[RISK_TIER_QUANTILES["high"]]
    mod  = q[RISK_TIER_QUANTILES["moderate"]]

    out = np.where(s >= crit, "critical",
          np.where(s >= high, "high",
          np.where(s >= mod,  "moderate", "low")))
    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_district_layer(
    facilities: pd.DataFrame,
    nfhs: pd.DataFrame,
    districts: gpd.GeoDataFrame,
    radius_km: float,
    need_formula: str = "default",
) -> gpd.GeoDataFrame:
    """Single-radius computation. Returns districts + scoring columns.

    NeedIndex resolution order:
      1. need_formula='volume_weighted' and births available -> NMR x SBA-gap x log(births)
      2. NMR available -> NMR x SBA-gap (canonical formula)
      3. NMR missing nationally -> proxy from SBA + Institutional Births + ANC4+
    """
    merged = join_nfhs_to_districts(districts, nfhs)

    nmr_available = merged["_nmr"].notna().any()
    if not nmr_available:
        merged["need_index"] = compute_need_index_proxy(
            merged["_sba"], merged["_institutional_births"], merged["_anc4_plus"],
        )
        merged["need_index_source"] = "proxy_sba_inst_anc"
        logger.info(
            "build_district_layer: NMR unavailable; using proxy NeedIndex "
            "(weights: SBA 0.5, Institutional Births 0.3, ANC4+ 0.2)"
        )
    elif need_formula == "volume_weighted":
        merged["need_index"] = compute_need_index_volume_weighted(
            merged["_nmr"], merged["_sba"], merged["_births"]
        )
        merged["need_index_source"] = "nmr_volume_weighted"
    else:
        merged["need_index"] = compute_need_index(merged["_nmr"], merged["_sba"])
        merged["need_index_source"] = "nmr_x_sba_gap"

    neon = facilities[facilities["_is_neonatal"]]

    coverage_quality, raw_sum, verified_count, dom_contradiction = \
        compute_coverage_quality(
            district_lats=merged["_lat"].to_numpy(),
            district_lons=merged["_lon"].to_numpy(),
            facility_lats=neon["_lat"].to_numpy(),
            facility_lons=neon["_lon"].to_numpy(),
            facility_weights=neon["_trust_weight"].to_numpy(),
            facility_trust_score=neon["_trust_score"].to_numpy(),
            facility_contradiction_type=neon["_contradiction_type"].to_numpy(),
            radius_km=radius_km,
        )

    merged["coverage_quality_score"] = coverage_quality
    merged["coverage_raw_sum"] = raw_sum
    merged["verified_facility_count"] = verified_count
    merged["total_facility_count"] = _total_facilities_in_radius(
        merged, facilities, radius_km
    )
    merged["dominant_contradiction_type"] = dom_contradiction
    merged["desert_score"] = compute_desert_score(
        merged["need_index"].values, merged["coverage_quality_score"].values
    )
    merged["risk_tier"] = assign_risk_tier(merged["desert_score"].values)
    merged["fill_color"] = pd.Series(merged["risk_tier"]).map(CHOROPLETH_HEX)
    merged["fill_opacity"] = pd.Series(merged["risk_tier"]).map(CHOROPLETH_OPACITY)
    return merged


def _total_facilities_in_radius(
    districts: gpd.GeoDataFrame, facilities: pd.DataFrame, radius_km: float
) -> np.ndarray:
    """All facilities (not just neonatal) inside radius  for the UI counter."""
    if len(facilities) == 0:
        return np.zeros(len(districts), dtype=int)
    fac_rad = np.deg2rad(facilities[["_lat", "_lon"]].to_numpy())
    dist_rad = np.deg2rad(districts[["_lat", "_lon"]].to_numpy())
    tree = BallTree(fac_rad, metric="haversine")
    radius = radius_km / EARTH_RADIUS_KM
    counts = tree.query_radius(dist_rad, r=radius, count_only=True)
    return counts.astype(int)


def build_multi_radius_topojson(
    facilities_path: str | Path,
    nfhs_path: str | Path,
    districts_path: str | Path,
    output_path: str | Path,
    radii_km: Sequence[int] = DEFAULT_RADII_KM,
    need_formula: str = "default",
) -> Path:
    """Full pipeline. Embeds desert/coverage/risk per radius as suffixed
    properties on each district feature."""
    if tp is None:
        raise ImportError(
            "topojson library not installed. `pip install topojson` "
            "(or use the topojson CLI to convert the intermediate GeoJSON)."
        )

    facilities = load_facilities(facilities_path)
    nfhs       = load_nfhs(nfhs_path)
    districts  = load_districts(districts_path)

    base = districts[
        ["_district_key", "_state_key", "_lat", "_lon", "geometry"]
    ].copy()
    # Find original-cased name columns for display
    display_cols = [c for c in districts.columns
                    if c.lower() in ("district", "dist_name", "dt_name", "name")]
    if display_cols:
        base["district"] = districts[display_cols[0]]
    else:
        base["district"] = districts["_district_key"]
    state_display = [c for c in districts.columns if c.lower() in ("state", "st_nm", "state_name")]
    base["state"] = districts[state_display[0]] if state_display else districts["_state_key"]

    # Static (radius-independent) properties from the first pass
    first_radius = radii_km[0]
    layer = build_district_layer(
        facilities, nfhs, districts, first_radius, need_formula
    )
    base["need_index"]                   = layer["need_index"].values
    base["need_index_source"]            = layer["need_index_source"].values
    base["neonatal_mortality_rate"]      = layer["_nmr"].values
    base["skilled_birth_attendance_pct"] = layer["_sba"].values
    base["institutional_births_pct"]     = layer["_institutional_births"].values
    base["anc4_plus_pct"]                = layer["_anc4_plus"].values
    base["nfhs_imputed"]                 = layer["nfhs_imputed"].astype(bool).values
    base["nfhs_match_quality"]           = layer["nfhs_match_quality"].values

    # Per-radius properties  suffixed
    for r in radii_km:
        layer_r = build_district_layer(
            facilities, nfhs, districts, r, need_formula
        )
        suffix = f"_{int(r)}km"
        base[f"coverage_quality_score{suffix}"]      = layer_r["coverage_quality_score"].values
        base[f"verified_facility_count{suffix}"]     = layer_r["verified_facility_count"].values
        base[f"total_facility_count{suffix}"]        = layer_r["total_facility_count"].values
        base[f"dominant_contradiction_type{suffix}"] = layer_r["dominant_contradiction_type"].values
        base[f"desert_score{suffix}"]                = layer_r["desert_score"].values
        base[f"risk_tier{suffix}"]                   = layer_r["risk_tier"].values
        base[f"fill_color{suffix}"]                  = layer_r["fill_color"].values
        base[f"fill_opacity{suffix}"]                = layer_r["fill_opacity"].values
        logger.info(
            "radius %d km  risk tier counts: %s",
            r, dict(Counter(layer_r["risk_tier"]))
        )

    out_gdf = gpd.GeoDataFrame(base, geometry="geometry", crs="EPSG:4326")

    # Drop internal _* helpers from final output
    drop = [c for c in out_gdf.columns if c.startswith("_")]
    out_gdf = out_gdf.drop(columns=drop)

    topo = tp.Topology(out_gdf, prequantize=False)
    output_path = Path(output_path)
    output_path.write_text(topo.to_json())
    logger.info("wrote TopoJSON to %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AXON Desert Score pipeline")
    p.add_argument("--facilities", required=True, help="Facility xlsx path")
    p.add_argument("--nfhs",       required=True, help="NFHS-5 districts CSV path")
    p.add_argument("--districts",  required=True, help="Districts.geojson path")
    p.add_argument("--out",        required=True, help="Output TopoJSON path")
    p.add_argument(
        "--radii", nargs="+", type=int, default=list(DEFAULT_RADII_KM),
        help="Radii in km (default: 30 60 120)",
    )
    p.add_argument(
        "--need-formula", choices=["default", "volume_weighted"],
        default="default",
        help="Need Index variant. 'volume_weighted' multiplies by log1p(births/1000).",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    build_multi_radius_topojson(
        facilities_path=args.facilities,
        nfhs_path=args.nfhs,
        districts_path=args.districts,
        output_path=args.out,
        radii_km=args.radii,
        need_formula=args.need_formula,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
