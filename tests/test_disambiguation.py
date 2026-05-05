"""End-to-end tests for the location-resolution helper in main.py."""
from __future__ import annotations

import httpx
import pytest
import respx

from main import GeocodeFailed, NotFound, Resolved, Disambiguation, _resolve_location


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class TestResolveLocation:
    @respx.mock
    @pytest.mark.asyncio
    async def test_qualified_single_match_uses_it(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        result = await _resolve_location(http_client, "Jupiter, FL")
        assert isinstance(result, Resolved)
        assert result.name == "Jupiter, Florida"
        assert result.latitude == pytest.approx(26.93423)
        assert result.longitude == pytest.approx(-80.0942)

    @respx.mock
    @pytest.mark.asyncio
    async def test_qualified_multiple_same_state_picks_higher_population(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_only_florida"))
        result = await _resolve_location(http_client, "Jupiter, FL")
        assert isinstance(result, Resolved)
        # The 61047 population entry beats the 425 population entry.
        assert result.latitude == pytest.approx(26.93)

    @respx.mock
    @pytest.mark.asyncio
    async def test_qualified_no_match_returns_disambiguation_with_3(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        result = await _resolve_location(http_client, "Jupiter, Mars")
        assert isinstance(result, Disambiguation)
        assert "Jupiter, Florida" in result.spoken
        assert "Or" in result.spoken
        assert result.spoken.startswith("I could not find Jupiter in Mars.")

    @respx.mock
    @pytest.mark.asyncio
    async def test_unqualified_multiple_returns_disambiguation_with_top_3_by_population(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_springfield"))
        result = await _resolve_location(http_client, "Springfield")
        assert isinstance(result, Disambiguation)
        # Top three by population: Missouri (169176), Massachusetts (153606), Illinois (116250).
        assert result.spoken == (
            "There are several places called Springfield. "
            "Did you mean Springfield, Missouri. Springfield, Massachusetts. Or Springfield, Illinois."
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_unqualified_single_result_uses_it(self, http_client) -> None:
        respx.get(GEOCODE_URL).respond(json={"results": [
            {"id": 1, "name": "Timbuktu", "latitude": 16.77, "longitude": -3.0,
             "country_code": "ML", "country": "Mali", "admin1": "Tombouctou", "population": 54000}
        ]})
        result = await _resolve_location(http_client, "Timbuktu")
        assert isinstance(result, Resolved)
        # Non-US -> 'name, country'
        assert result.name == "Timbuktu, Mali"

    @respx.mock
    @pytest.mark.asyncio
    async def test_zero_results_returns_not_found(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_empty"))
        result = await _resolve_location(http_client, "Springfield, Mars")
        assert isinstance(result, NotFound)
        assert result.spoken == (
            "I could not find a place called Springfield, Mars. Please try a different city name."
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_state_abbreviation_expansion(self, http_client) -> None:
        respx.get(GEOCODE_URL).respond(json={"results": [
            {"id": 1, "name": "East Hanover", "latitude": 40.82, "longitude": -74.36,
             "country_code": "US", "country": "United States", "admin1": "New Jersey", "population": 11144}
        ]})
        result = await _resolve_location(http_client, "East Hanover, NJ")
        assert isinstance(result, Resolved)
        assert result.name == "East Hanover, New Jersey"

    @respx.mock
    @pytest.mark.asyncio
    async def test_non_us_qualifier_matches_country_name(self, http_client) -> None:
        respx.get(GEOCODE_URL).respond(json={"results": [
            {"id": 1, "name": "Paris", "latitude": 48.85, "longitude": 2.35,
             "country_code": "FR", "country": "France", "admin1": "Île-de-France", "population": 2148327},
            {"id": 2, "name": "Paris", "latitude": 33.66, "longitude": -95.55,
             "country_code": "US", "country": "United States", "admin1": "Texas", "population": 24782},
        ]})
        result = await _resolve_location(http_client, "Paris, France")
        assert isinstance(result, Resolved)
        assert result.name == "Paris, France"
        assert result.latitude == pytest.approx(48.85)

    @respx.mock
    @pytest.mark.asyncio
    async def test_non_us_qualifier_matches_country_code(self, http_client) -> None:
        respx.get(GEOCODE_URL).respond(json={"results": [
            {"id": 1, "name": "Paris", "latitude": 48.85, "longitude": 2.35,
             "country_code": "FR", "country": "France", "admin1": "Île-de-France", "population": 2148327},
            {"id": 2, "name": "Paris", "latitude": 33.66, "longitude": -95.55,
             "country_code": "US", "country": "United States", "admin1": "Texas", "population": 24782},
        ]})
        result = await _resolve_location(http_client, "Paris, FR")
        assert isinstance(result, Resolved)
        assert result.name == "Paris, France"

    @respx.mock
    @pytest.mark.asyncio
    async def test_geocoder_http_error_returns_geocode_failed(self, http_client) -> None:
        respx.get(GEOCODE_URL).respond(status_code=503)
        result = await _resolve_location(http_client, "Anywhere")
        assert isinstance(result, GeocodeFailed)
        assert result.spoken == (
            "I had trouble looking up that location. Please try again in a moment."
        )
