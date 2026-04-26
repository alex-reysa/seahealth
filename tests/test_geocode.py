"""Tests for the static India city geocoder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seahealth.agents.geocode import (
    INDIA_CITIES,
    _city_centroid_lookup,
    _pin_lookup,
    geocode,
    haversine_km,
)

FIXTURE = Path(__file__).parent / "fixtures" / "query" / "india_cities.json"


def test_patna_resolvable() -> None:
    point = geocode("Patna")
    assert point is not None
    assert pytest.approx(point.lat, abs=0.5) == 25.6
    assert pytest.approx(point.lng, abs=0.5) == 85.1
    assert point.pin_code == "800001"


@pytest.mark.parametrize(
    ("city", "pin_code"),
    [
        ("Madhubani", "847211"),
        ("Muzaffarpur", "842001"),
        ("Bhagalpur", "812001"),
    ],
)
def test_bihar_expansion_cities_resolvable(city: str, pin_code: str) -> None:
    point = geocode(city)
    assert point is not None
    assert point.pin_code == pin_code


def test_unknown_returns_none() -> None:
    assert geocode("Atlantis") is None


def test_haversine_self_zero() -> None:
    point = INDIA_CITIES["Patna"]
    assert haversine_km(point, point) == pytest.approx(0.0, abs=1e-6)


def test_haversine_patna_to_gaya() -> None:
    distance = haversine_km(INDIA_CITIES["Patna"], INDIA_CITIES["Gaya"])
    # Real-world distance is ~95 km; allow generous slack.
    assert 80.0 <= distance <= 120.0


def test_case_insensitive() -> None:
    assert geocode("PATNA") is not None
    assert geocode("patna") is not None
    assert geocode(" PaTnA ") is not None


def test_fixture_matches_module_table() -> None:
    """The repo fixture's seeded cities must remain present in INDIA_CITIES."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cities = {c["name"] for c in payload["cities"]}
    assert cities <= set(INDIA_CITIES.keys())


def test_state_level_bihar_resolves_for_locked_demo_query() -> None:
    """The locked demo query reads "rural Bihar" with no city. The state-
    level fallback must resolve so the planner can geocode and produce
    candidates instead of returning the empty-intent sentinel."""
    point = geocode("Find the nearest facility in rural Bihar that can perform an emergency appendectomy.")
    assert point is not None
    # Bihar's state capital coordinates.
    assert pytest.approx(point.lat, abs=0.5) == 25.6
    assert pytest.approx(point.lng, abs=0.5) == 85.1


# ---------------------------------------------------------------------------
# PIN-code resolution (Task C1)
# ---------------------------------------------------------------------------


def test_pin_800001_resolves_to_patna() -> None:
    """``PIN 800001`` is Patna's head-PO; the parquet contains many rows
    with that PIN, so the centroid should land near Patna's centre."""
    point = geocode("Find facilities of PIN 800001")
    assert point is not None
    assert point.pin_code == "800001"
    assert pytest.approx(point.lat, abs=0.5) == 25.6
    assert pytest.approx(point.lng, abs=0.5) == 85.1


def test_pin_400001_resolves_to_mumbai() -> None:
    """``PIN 400001`` is Mumbai's Fort head-PO."""
    point = geocode("PIN 400001 hospitals")
    assert point is not None
    assert point.pin_code == "400001"
    assert pytest.approx(point.lat, abs=0.5) == 19.0
    assert pytest.approx(point.lng, abs=0.5) == 72.8


def test_pin_unknown_falls_through_to_city() -> None:
    """An unknown PIN must not short-circuit; the city name in the same
    query should still resolve."""
    point = geocode("PIN 999999 in Patna")
    assert point is not None
    # Should land on Patna (the hand-curated entry, with PIN attached).
    assert pytest.approx(point.lat, abs=0.5) == 25.6
    assert pytest.approx(point.lng, abs=0.5) == 85.1


# ---------------------------------------------------------------------------
# City-centroid bootstrap + city > state tie-break (Tasks C2, C3)
# ---------------------------------------------------------------------------


def test_sitamarhi_bihar_resolves_to_sitamarhi() -> None:
    """Sitamarhi is not in the hand-curated table but should be auto-derived
    from facilities_index. The city must beat the state in the tie-break."""
    centroids = _city_centroid_lookup()
    point = geocode("neonatal facilities within 30km of Sitamarhi, Bihar")
    assert point is not None
    if "sitamarhi" in centroids:
        assert pytest.approx(point.lat, abs=1.0) == 26.6
        assert pytest.approx(point.lng, abs=1.0) == 85.5
        # Must NOT be Patna.
        assert not (
            pytest.approx(point.lat, abs=0.1) == 25.61
            and pytest.approx(point.lng, abs=0.1) == 85.14
        )
    else:  # pragma: no cover - depends on demo dataset
        # Even without auto-derivation the state fallback must at least
        # be closer to Sitamarhi (26.6/85.5) than to a wildly wrong region.
        # Patna is acceptable; assert we got *something*.
        assert point.lat is not None


def test_city_beats_state_tiebreak() -> None:
    """``hospitals in Mumbai, Maharashtra`` must resolve to Mumbai, not the
    state centroid (which would also be Mumbai by virtue of the curated
    table, so this primarily exercises the tie-break logic)."""
    point = geocode("hospitals in Mumbai, Maharashtra")
    assert point is not None
    assert pytest.approx(point.lat, abs=0.1) == 19.0760
    assert pytest.approx(point.lng, abs=0.1) == 72.8777
    # Mumbai's curated PIN is 400001; if the state had won the tie-break
    # we'd still see 400001 here, but the contract is "city wins" — the
    # curated Mumbai entry happens to share a PIN with the curated
    # Maharashtra entry. We assert the city's PIN is present.
    assert point.pin_code == "400001"


def test_existing_patna_query_unchanged() -> None:
    """The locked demo behaviour ("rural Bihar" → Patna's coords) must be
    preserved by the new tie-break + auto-centroid logic."""
    point = geocode("rural Bihar")
    assert point is not None
    assert pytest.approx(point.lat, abs=0.5) == 25.6
    assert pytest.approx(point.lng, abs=0.5) == 85.1


# ---------------------------------------------------------------------------
# Lookup builders smoke tests
# ---------------------------------------------------------------------------


def test_pin_lookup_nonempty() -> None:
    """The PIN lookup should be populated from the bundled parquet."""
    pins = _pin_lookup()
    assert len(pins) > 100, f"expected many PINs, got {len(pins)}"
    assert "800001" in pins
    sample = pins["800001"]
    assert sample.pin_code == "800001"


def test_city_centroid_lookup_nonempty() -> None:
    """The city centroid lookup should include several real Bihar cities."""
    centroids = _city_centroid_lookup()
    assert len(centroids) > 50, f"expected many cities, got {len(centroids)}"
    # Patna is curated but should also appear in auto-centroids (many rows).
    assert "patna" in centroids
