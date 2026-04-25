"""Static India city -> GeoPoint resolver used by the Query Agent.

This module deliberately avoids any network calls. The hackathon demo only
needs to resolve a closed set of major Indian cities; we hand-curate the
table here so the Query Agent stays deterministic and testable without an
external geocoding service.
"""

from __future__ import annotations

import math

from seahealth.schemas import GeoPoint

# Hand-curated lat/lng/PIN for the demo cities. Coordinates are approximate
# city-centre values; PIN codes are representative head-PO 6-digit codes.
INDIA_CITIES: dict[str, GeoPoint] = {
    "Patna": GeoPoint(lat=25.61, lng=85.14, pin_code="800001"),
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
}


_EARTH_RADIUS_KM = 6371.0088


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Return the great-circle distance between two GeoPoints in kilometres."""
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def geocode(query: str) -> GeoPoint | None:
    """Return a GeoPoint for a known Indian city.

    Match strategy:

    * Case-insensitive.
    * Trimmed substring match — the city name must appear as a substring of
      the query (or vice-versa). Exact matches win, then the longest known
      city that appears as a substring of ``query`` wins.

    Returns None if no city matches. Tests rely on Patna being matchable.
    """
    if not query:
        return None
    q = query.strip().lower()
    if not q:
        return None

    # Exact match (case-insensitive) wins immediately.
    for name, point in INDIA_CITIES.items():
        if q == name.lower():
            return point

    # Otherwise pick the longest city name that appears as a substring of the
    # query — this beats grabbing 'Gaya' out of a query mentioning 'Patna'.
    best_match: tuple[int, GeoPoint] | None = None
    for name, point in INDIA_CITIES.items():
        lname = name.lower()
        if lname in q or q in lname:
            score = len(lname)
            if best_match is None or score > best_match[0]:
                best_match = (score, point)
    return best_match[1] if best_match else None


__all__ = ["INDIA_CITIES", "geocode", "haversine_km"]
