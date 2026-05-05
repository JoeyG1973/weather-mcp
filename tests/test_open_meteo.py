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


from open_meteo import fetch_current, fetch_forecast


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class TestFetchCurrent:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_payload(self, http_client: httpx.AsyncClient, fixture) -> None:
        respx.get(FORECAST_URL).respond(json=fixture("current_jupiter"))
        payload = await fetch_current(http_client, lat=26.93, lon=-80.09)
        assert payload["current"]["temperature_2m"] == pytest.approx(78.4)

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_expected_query_params(self, http_client: httpx.AsyncClient, fixture) -> None:
        route = respx.get(FORECAST_URL).respond(json=fixture("current_jupiter"))
        await fetch_current(http_client, lat=26.93, lon=-80.09)
        params = route.calls.last.request.url.params
        assert params["latitude"] == "26.93"
        assert params["longitude"] == "-80.09"
        # 'current=' must list every field the formatter consumes.
        current_fields = set(params["current"].split(","))
        assert current_fields == {
            "temperature_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m",
        }
        assert params["temperature_unit"] == "fahrenheit"
        assert params["wind_speed_unit"] == "mph"
        assert params["precipitation_unit"] == "inch"

    @respx.mock
    @pytest.mark.asyncio
    async def test_http_error_raises(self, http_client: httpx.AsyncClient) -> None:
        respx.get(FORECAST_URL).respond(status_code=500)
        with pytest.raises(OpenMeteoError):
            await fetch_current(http_client, lat=0.0, lon=0.0)


class TestFetchForecast:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_payload(self, http_client: httpx.AsyncClient, fixture) -> None:
        respx.get(FORECAST_URL).respond(json=fixture("forecast_jupiter_3day"))
        payload = await fetch_forecast(http_client, lat=26.93, lon=-80.09, days=3)
        assert len(payload["daily"]["time"]) == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_expected_query_params(self, http_client: httpx.AsyncClient, fixture) -> None:
        route = respx.get(FORECAST_URL).respond(json=fixture("forecast_jupiter_3day"))
        await fetch_forecast(http_client, lat=26.93, lon=-80.09, days=3)
        params = route.calls.last.request.url.params
        assert params["latitude"] == "26.93"
        assert params["longitude"] == "-80.09"
        daily_fields = set(params["daily"].split(","))
        assert daily_fields == {
            "temperature_2m_max",
            "temperature_2m_min",
            "weather_code",
            "precipitation_probability_max",
        }
        assert params["forecast_days"] == "3"
        assert params["temperature_unit"] == "fahrenheit"
        assert params["wind_speed_unit"] == "mph"
        assert params["precipitation_unit"] == "inch"

    @respx.mock
    @pytest.mark.asyncio
    async def test_http_error_raises(self, http_client: httpx.AsyncClient) -> None:
        respx.get(FORECAST_URL).respond(status_code=400)
        with pytest.raises(OpenMeteoError):
            await fetch_forecast(http_client, lat=0.0, lon=0.0, days=3)
