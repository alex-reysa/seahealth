"""Tests for the static India city geocoder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seahealth.agents.geocode import INDIA_CITIES, geocode, haversine_km

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
