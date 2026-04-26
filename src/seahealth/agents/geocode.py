"""Static India city -> GeoPoint resolver used by the Query Agent.

This module deliberately avoids any network calls. The hackathon demo only
needs to resolve a closed set of major Indian cities; we hand-curate the
table here so the Query Agent stays deterministic and testable without an
external geocoding service.

In addition to the hand-curated table, the geocoder lazily builds two
lookups from ``tables/facilities_index.parquet`` so that:

* 6-digit PIN codes mentioned in queries (``PIN 800001`` / bare ``800001``)
  resolve to the centroid of all facilities with that PIN.
* City names not present in the curated table (e.g. ``Sitamarhi``) resolve
  to the centroid of all facilities in that city, provided there are at
  least two recorded facilities (to suppress single-row noise).

Both lookups are cached via :func:`functools.lru_cache` so the parquet file
is read at most once per process.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

import pyarrow.parquet as pq

from seahealth.schemas import GeoPoint

# Hand-curated lat/lng/PIN for the demo cities. Coordinates are approximate
# city-centre values; PIN codes are representative head-PO 6-digit codes.
INDIA_CITIES: dict[str, GeoPoint] = {
    "Patna": GeoPoint(lat=25.61, lng=85.14, pin_code="800001"),
    "Madhubani": GeoPoint(lat=26.3483, lng=86.0712, pin_code="847211"),
    "Muzaffarpur": GeoPoint(lat=26.1226, lng=85.3906, pin_code="842001"),
    "Bhagalpur": GeoPoint(lat=25.2425, lng=86.9842, pin_code="812001"),
    "Delhi": GeoPoint(lat=28.6139, lng=77.2090, pin_code="110001"),
    "Mumbai": GeoPoint(lat=19.0760, lng=72.8777, pin_code="400001"),
    "Bengaluru": GeoPoint(lat=12.9716, lng=77.5946, pin_code="560001"),
    "Kolkata": GeoPoint(lat=22.5726, lng=88.3639, pin_code="700001"),
    "Chennai": GeoPoint(lat=13.0827, lng=80.2707, pin_code="600001"),
    "Hyderabad": GeoPoint(lat=17.3850, lng=78.4867, pin_code="500001"),
    "Lucknow": GeoPoint(lat=26.8467, lng=80.9462, pin_code="226001"),
    "Bhopal": GeoPoint(lat=23.2599, lng=77.4126, pin_code="462001"),
    "Ranchi": GeoPoint(lat=23.3441, lng=85.3096, pin_code="834001"),
    "Varanasi": GeoPoint(lat=25.3176, lng=82.9739, pin_code="221001"),
    "Gaya": GeoPoint(lat=24.7914, lng=85.0002, pin_code="823001"),
    # State-level fallbacks resolve to the state capital. The locked demo
    # query reads "rural Bihar"; without these the heuristic geocoder fails
    # the parse_intent step and the planner returns zero candidates. The
    # first 6-digit PIN below is the state capital's head-PO.
    "Bihar": GeoPoint(lat=25.61, lng=85.14, pin_code="800001"),
    "Uttar Pradesh": GeoPoint(lat=26.8467, lng=80.9462, pin_code="226001"),
    "Maharashtra": GeoPoint(lat=19.0760, lng=72.8777, pin_code="400001"),
    "Karnataka": GeoPoint(lat=12.9716, lng=77.5946, pin_code="560001"),
    "West Bengal": GeoPoint(lat=22.5726, lng=88.3639, pin_code="700001"),
    "Tamil Nadu": GeoPoint(lat=13.0827, lng=80.2707, pin_code="600001"),
    "Telangana": GeoPoint(lat=17.3850, lng=78.4867, pin_code="500001"),
    "Madhya Pradesh": GeoPoint(lat=23.2599, lng=77.4126, pin_code="462001"),
    "Jharkhand": GeoPoint(lat=23.3441, lng=85.3096, pin_code="834001"),
}

# Names in INDIA_CITIES that are states rather than cities. The substring
# tie-break boosts city matches over state matches by +1000.
_INDIA_STATES: set[str] = {
    "Bihar",
    "Uttar Pradesh",
    "Maharashtra",
    "Karnataka",
    "West Bengal",
    "Tamil Nadu",
    "Telangana",
    "Madhya Pradesh",
    "Jharkhand",
}


_EARTH_RADIUS_KM = 6371.0088

# Default path mirrors ``tools.DEFAULT_FACILITIES_INDEX_PATH``. We resolve
# relative to the working directory so callers (CLI, tests) don't have to
# pass the path explicitly.
_DEFAULT_FACILITIES_INDEX_PATH = "tables/facilities_index.parquet"

_PIN_PREFIX_RE = re.compile(r"(?:pin\s*code|pincode|pin)\s*[:\-]?\s*(\d{6})", re.IGNORECASE)
_BARE_PIN_RE = re.compile(r"\b(\d{6})\b")


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Return the great-circle distance between two GeoPoints in kilometres."""
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def _resolve_facilities_path(path: str | None = None) -> Path:
    """Resolve the parquet path; defaults to the repo-relative location."""
    return Path(path) if path else Path(_DEFAULT_FACILITIES_INDEX_PATH)


@lru_cache(maxsize=4)
def _pin_lookup(facilities_path: str | None = None) -> dict[str, GeoPoint]:
    """Return a {pin_string: GeoPoint} map keyed by 6-digit PIN.

    Each value is the mean of the lat/lng of every facility carrying that
    PIN in ``facilities_index.parquet``. Empty / unreadable parquet ⇒ {}.
    """
    path = _resolve_facilities_path(facilities_path)
    if not path.exists():
        return {}
    try:
        table = pq.read_table(path, columns=["pin_code", "latitude", "longitude"])
    except Exception:
        return {}
    pins = table.column("pin_code").to_pylist()
    lats = table.column("latitude").to_pylist()
    lngs = table.column("longitude").to_pylist()
    buckets: dict[str, list[tuple[float, float]]] = {}
    for pin, lat, lng in zip(pins, lats, lngs, strict=True):
        if pin is None or lat is None or lng is None:
            continue
        key = str(pin).strip()
        if not key or not key.isdigit() or len(key) != 6:
            continue
        try:
            buckets.setdefault(key, []).append((float(lat), float(lng)))
        except (TypeError, ValueError):
            continue
    out: dict[str, GeoPoint] = {}
    for key, points in buckets.items():
        if not points:
            continue
        mean_lat = sum(p[0] for p in points) / len(points)
        mean_lng = sum(p[1] for p in points) / len(points)
        try:
            out[key] = GeoPoint(lat=mean_lat, lng=mean_lng, pin_code=key)
        except Exception:
            # Skip rows whose averaged coords fall outside valid ranges
            # (shouldn't happen with real data but keeps us robust).
            continue
    return out


@lru_cache(maxsize=4)
def _city_centroid_lookup(facilities_path: str | None = None) -> dict[str, GeoPoint]:
    """Return a {lowercased_city: GeoPoint} map for cities with >= 2 facilities.

    Single-facility cities are skipped to suppress noise (a single mis-tagged
    row could otherwise yield a misleading centroid). The hand-curated
    INDIA_CITIES table takes precedence over this lookup.
    """
    path = _resolve_facilities_path(facilities_path)
    if not path.exists():
        return {}
    try:
        table = pq.read_table(
            path, columns=["address_city", "latitude", "longitude"]
        )
    except Exception:
        return {}
    cities = table.column("address_city").to_pylist()
    lats = table.column("latitude").to_pylist()
    lngs = table.column("longitude").to_pylist()
    buckets: dict[str, list[tuple[float, float]]] = {}
    for city, lat, lng in zip(cities, lats, lngs, strict=True):
        if not city or lat is None or lng is None:
            continue
        key = str(city).strip().lower()
        if not key:
            continue
        try:
            buckets.setdefault(key, []).append((float(lat), float(lng)))
        except (TypeError, ValueError):
            continue
    out: dict[str, GeoPoint] = {}
    for key, points in buckets.items():
        if len(points) < 2:
            continue
        mean_lat = sum(p[0] for p in points) / len(points)
        mean_lng = sum(p[1] for p in points) / len(points)
        try:
            out[key] = GeoPoint(lat=mean_lat, lng=mean_lng)
        except Exception:
            continue
    return out


def _extract_pin(query: str) -> str | None:
    """Return a 6-digit PIN found in ``query``, or ``None``.

    The explicit ``PIN <digits>`` / ``pincode <digits>`` form takes
    precedence over a bare 6-digit token; the bare form only fires if
    there's exactly one such token in the query (so we don't accidentally
    grab a postal-looking number from "30km" or year/phone numbers).
    """
    if not query:
        return None
    m = _PIN_PREFIX_RE.search(query)
    if m:
        return m.group(1)
    bare = _BARE_PIN_RE.findall(query)
    if len(bare) == 1:
        return bare[0]
    return None


def geocode(query: str) -> GeoPoint | None:
    """Return a GeoPoint for a known Indian PIN, city, or state.

    Resolution order:

    1. Explicit ``PIN <6 digits>`` (or unique bare 6-digit number) → mean
       lat/lng of all facilities with that PIN in the index.
    2. Exact case-insensitive match in the hand-curated ``INDIA_CITIES``.
    3. Exact case-insensitive match in the auto-derived city centroids
       built from ``facilities_index.parquet``.
    4. Substring fallback over the union of the above name sets, with
       city matches scored +1000 above state matches so e.g.
       ``Sitamarhi, Bihar`` resolves to Sitamarhi rather than Bihar.

    Returns None if nothing matches.
    """
    if not query:
        return None
    q = query.strip()
    if not q:
        return None

    # 1) PIN-code pre-pass.
    pin = _extract_pin(q)
    if pin is not None:
        pin_map = _pin_lookup()
        if pin in pin_map:
            return pin_map[pin]
        # Unknown PIN → fall through to city/state matching.

    qlower = q.lower()

    # 2) Exact match in the hand-curated table.
    for name, point in INDIA_CITIES.items():
        if qlower == name.lower():
            return point

    # 3) Exact match in auto-derived city centroids.
    centroid_map = _city_centroid_lookup()
    if qlower in centroid_map:
        return centroid_map[qlower]

    # 4) Substring fallback. Score = name length, +1000 if it's a city
    #    (so a city wins over any state in queries like "Sitamarhi, Bihar").
    state_names_lower = {s.lower() for s in _INDIA_STATES}
    best_match: tuple[int, GeoPoint] | None = None

    def _consider(name_lower: str, point: GeoPoint, *, is_state: bool) -> None:
        nonlocal best_match
        if name_lower in qlower or qlower in name_lower:
            score = len(name_lower) + (0 if is_state else 1000)
            if best_match is None or score > best_match[0]:
                best_match = (score, point)

    for name, point in INDIA_CITIES.items():
        lname = name.lower()
        _consider(lname, point, is_state=name in _INDIA_STATES)

    for name_lower, point in centroid_map.items():
        # Auto-derived entries are never states by construction. Skip if
        # the name collides with a hand-curated state to avoid a
        # surprising override (state-name and city-of-same-name conflict
        # is rare in the demo data).
        if name_lower in state_names_lower:
            continue
        _consider(name_lower, point, is_state=False)

    return best_match[1] if best_match else None


__all__ = ["INDIA_CITIES", "geocode", "haversine_km"]
