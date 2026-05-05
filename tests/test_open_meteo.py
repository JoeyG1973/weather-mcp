"""Tests for the Open-Meteo I/O layer."""
from __future__ import annotations

import httpx
import pytest
import respx

from open_meteo import GeocodeMatch, OpenMeteoError, geocode


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class TestGeocode:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_parsed_matches(self, http_client: httpx.AsyncClient, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        matches = await geocode(http_client, "Jupiter, FL")
        assert len(matches) == 3
        m = matches[0]
        assert isinstance(m, GeocodeMatch)
        assert m.name == "Jupiter"
        assert m.admin1 == "Florida"
        assert m.country == "United States"
        assert m.country_code == "US"
        assert m.latitude == pytest.approx(26.93423)
        assert m.longitude == pytest.approx(-80.0942)
        assert m.population == 61047

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_expected_query_params(self, http_client: httpx.AsyncClient, fixture) -> None:
        route = respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        await geocode(http_client, "Jupiter, FL")
        request = route.calls.last.request
        assert request.url.params["name"] == "Jupiter, FL"
        assert request.url.params["count"] == "10"
        assert request.url.params["language"] == "en"
        assert request.url.params["format"] == "json"

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self, http_client: httpx.AsyncClient, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_empty"))
        assert await geocode(http_client, "Springfield, Mars") == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_http_error_raises_open_meteo_error(self, http_client: httpx.AsyncClient) -> None:
        respx.get(GEOCODE_URL).respond(status_code=503)
        with pytest.raises(OpenMeteoError):
            await geocode(http_client, "Anywhere")

    @respx.mock
    @pytest.mark.asyncio
    async def test_network_error_raises_open_meteo_error(self, http_client: httpx.AsyncClient) -> None:
        respx.get(GEOCODE_URL).mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(OpenMeteoError):
            await geocode(http_client, "Anywhere")

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_missing_optional_fields(self, http_client: httpx.AsyncClient) -> None:
        # Some Open-Meteo geocoder rows may omit admin1 or population for very small places.
        payload = {
            "results": [
                {"id": 99, "name": "Nowhere", "latitude": 0.0, "longitude": 0.0, "country_code": "ZZ", "country": "Atlantis"}
            ]
        }
        respx.get(GEOCODE_URL).respond(json=payload)
        matches = await geocode(http_client, "Nowhere")
        assert matches[0].admin1 is None
        assert matches[0].population == 0
