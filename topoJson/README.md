# Layer-2: Desert Score Pipeline

Turns the Layer-1 facility audits (with TrustScores) plus NFHS-5 district health indicators into a single TopoJSON intended to be consumed by the React Map Workbench as a choropleth of healthcare deserts.

For each Indian district and each radius (30 / 60 / 120 km) we compute:

```
NeedIndex          = neonatal need signal (NMR x SBA-gap, or proxy)
CoverageQuality    = sum( TrustWeight x facility ) / saturation, capped at 1
DesertScore       = NeedIndex / (CoverageQuality + epsilon)
RiskTier          = quantile-binned DesertScore (low / moderate / high / critical)
```

The output TopoJSON carries those values per district and per radius, alongside the dominant contradiction type observed inside each radius — so a click on a red district can show *why* the coverage signal is weak.

## Inputs

| File | Notes |
|---|---|
| `Districts.geojson.txt` | 641 Indian district polygons. Census-2011 codes (`ST_CEN_CD`, `DT_CEN_CD`) are the canonical join key. |
| `nfhs5_districts.csv` | NFHS-5 indicators per district, **long format** (one row per indicator). The loader auto-pivots and uses `NFHS 5` values with `NFHS 4` as fallback. |
| `<facilities>.xlsx` | Produced by the upstream agent layer (Extractor + Validator + Trust Scorer). Schema below. |

### Facilities xlsx — required columns

| Column (default header) | Type | Notes |
|---|---|---|
| `lat`, `lon` | float | India bbox (lat 6-38, lon 68-98). Rows outside are dropped. |
| `trustScore` | enum | One of `supports`, `unclear`, `contradicts`, `silent`. Unknown values map to `silent`. |
| `specialties`, `capability` | text / list | Free text; neonatal-relevance is detected from these (NICU, neonatology, obstetrics, maternity, etc.). |
| `facilityTypeId` | string | Pass-through. |
| `contradictionType` | string | Optional. Used to surface the dominant contradiction type per region. |

Pass `cols={...}` to `load_facilities()` to remap if your xlsx uses different headers.

## Run

```bash
pip install -r requirements.txt

python desert_score_model.py \
    --facilities path/to/VF_Hackathon_Dataset_India_Large.xlsx \
    --nfhs nfhs5_districts.csv \
    --districts Districts.geojson.txt \
    --out india_desert_layer.topojson
```

> **macOS / geopandas note:** `pip install geopandas` builds against system GDAL/PROJ. If install fails, run `brew install gdal proj` first. Linux users typically need `apt install libgdal-dev libproj-dev`. The scoring path (BallTree, Trust weighting, NeedIndex) is testable without geopandas — only the GeoJSON loader and TopoJSON exporter need it.

Optional flags:

- `--radii 30 60 120` — radii (km) to compute coverage at. Each lands as a suffixed property block on every district.
- `--need-formula default|volume_weighted` — `volume_weighted` multiplies the canonical NMR-based NeedIndex by `log1p(births / 1000)` where birth volume is available.
- `--log-level INFO|DEBUG` — pipeline emits district join stats and risk-tier counts per radius.

## Output schema

Each district feature carries:

**Static (radius-independent):**

| Property | Source |
|---|---|
| `district`, `state` | from the geojson display columns |
| `need_index` | the value used in DesertScore |
| `need_index_source` | which formula produced it (see below) |
| `neonatal_mortality_rate` | NFHS-5 NMR (NaN when not in source CSV) |
| `skilled_birth_attendance_pct` | NFHS-5 SBA |
| `institutional_births_pct` | NFHS-5 |
| `anc4_plus_pct` | NFHS-5 antenatal care, 4+ visits |
| `nfhs_imputed` | `true` iff **any** indicator on this row needed state-mean or national-mean imputation. A direct/name match with complete indicators is `false`. |
| `nfhs_match_quality` | One of `direct` (matched by Census codes), `name_fallback` (matched by normalized district + state name), `state_mean` (no row match; state-mean used), `national_mean` (state had no data either). The UI should drive a confidence indicator off this field. |

**Per-radius (suffix `_30km`, `_60km`, `_120km`):**

`coverage_quality_score`, `verified_facility_count`, `total_facility_count`, `dominant_contradiction_type`, `desert_score`, `risk_tier`, `fill_color`, `fill_opacity`.

### `need_index_source` values

| Value | When |
|---|---|
| `nmr_x_sba_gap` | Canonical formula: `NMR * (1 - SBA/100)`. Fires when the source CSV has district-level NMR. |
| `nmr_volume_weighted` | `--need-formula volume_weighted` plus births volume present. |
| `proxy_sba_inst_anc` | Automatic fallback when NMR is unavailable. The current NFHS-5 districts release omits NMR, so this is the active path. Combination: `0.5 * SBA-gap + 0.3 * InstitutionalBirths-gap + 0.2 * ANC4+-gap`, scaled to 0-100 to match typical NMR magnitudes (~10-50). |

The `need_index_source` field is the audit trail — judges can see exactly which signal drives the visualization for each district.

## Trust weights

Defined in `desert_score_model.py` and applied to every facility's contribution to `CoverageQuality`:

| TrustScore | Weight |
|---|---|
| `supports` | 1.00 |
| `unclear` | 0.50 |
| `contradicts` | 0.10 |
| `silent` | 0.05 |

A claim that contradicts the evidence is *not* nullified — it's heavily down-weighted. This is the methodology that lets the choropleth hold a defensible position on uncertainty without false precision.

## Data sources

- **NFHS-5 District Fact Sheets** — International Institute for Population Sciences (IIPS), 2019-21 round.
- **India district polygons** — Census of India 2011 administrative boundaries.

Both files are checked in (`!topoJson/*.csv` exception in repo `.gitignore`) so the pipeline runs from a clean clone.

## Tests

`test_smoke.py` covers the scoring path (coverage quality, proxy NeedIndex, desert score, risk tiers, trust-weight ordering, neonatal token detection) with synthetic fixtures so a regression in any of them is caught without needing real facility data:

```bash
python test_smoke.py            # standalone runner, no pytest required
python -m pytest test_smoke.py  # if pytest is installed
```

The data-loading / Census-code join half is exercised against real `nfhs5_districts.csv` + `Districts.geojson.txt` interactively — see the docstring in `desert_score_model.py` for the verification snippet.
