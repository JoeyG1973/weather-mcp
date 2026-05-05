"""Tests for the MCP tool functions, calling them directly as async functions."""
from __future__ import annotations

import httpx
import pytest
import respx

from main import get_current_weather, get_forecast


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class TestGetCurrentWeather:
    @respx.mock
    @pytest.mark.asyncio
    async def test_happy_path(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        respx.get(FORECAST_URL).respond(json=fixture("current_jupiter"))
        out = await get_current_weather(http_client, "Jupiter, FL")
        assert "In Jupiter, Florida, it is currently" in out
        assert "78 degrees" in out
        assert "partly cloudy skies" in out

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_input_prose(self, http_client) -> None:
        out = await get_current_weather(http_client, "")
        assert out == "I need a city name to look up the weather."

    @respx.mock
    @pytest.mark.asyncio
    async def test_whitespace_input_returns_empty_input_prose(self, http_client) -> None:
        out = await get_current_weather(http_client, "   ")
        assert out == "I need a city name to look up the weather."

    @respx.mock
    @pytest.mark.asyncio
    async def test_disambiguation_returns_did_you_mean(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_springfield"))
        # Note: NO forecast route registered. If get_current_weather erroneously calls
        # the forecast endpoint when disambiguation triggers, respx will raise.
        out = await get_current_weather(http_client, "Springfield")
        assert out.startswith("There are several places called Springfield.")

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found_returns_not_found_prose(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_empty"))
        out = await get_current_weather(http_client, "Springfield, Mars")
        assert out.startswith("I could not find a place called Springfield, Mars.")

    @respx.mock
    @pytest.mark.asyncio
    async def test_geocode_error_returns_geocode_error_prose(self, http_client) -> None:
        respx.get(GEOCODE_URL).respond(status_code=503)
        out = await get_current_weather(http_client, "Anywhere")
        assert out == "I had trouble looking up that location. Please try again in a moment."

    @respx.mock
    @pytest.mark.asyncio
    async def test_weather_error_after_resolved_returns_weather_error_prose(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        respx.get(FORECAST_URL).respond(status_code=500)
        out = await get_current_weather(http_client, "Jupiter, FL")
        assert out == (
            "I found Jupiter, Florida, but I had trouble getting the weather for it. "
            "Please try again in a moment."
        )


class TestGetForecast:
    @respx.mock
    @pytest.mark.asyncio
    async def test_happy_path_three_days(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        respx.get(FORECAST_URL).respond(json=fixture("forecast_jupiter_3day"))
        out = await get_forecast(http_client, "Jupiter, FL", 3)
        assert out.startswith("Here is the 3 day forecast for Jupiter, Florida.")
        assert "Tomorrow, " in out

    @respx.mock
    @pytest.mark.asyncio
    async def test_clamp_above_14(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        # When days clamps to 14, the implementation calls the API with days=14.
        # We don't have a 14-day fixture; the formatter doesn't care which N as long
        # as the daily arrays match. Reuse the 10-day fixture and assert just the prefix.
        respx.get(FORECAST_URL).respond(json=fixture("forecast_jupiter_10day"))
        out = await get_forecast(http_client, "Jupiter, FL", 30)
        assert out.startswith(
            "I can only forecast up to 14 days out, so here is the"
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_clamp_below_1(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        # days=-3 -> clamp to 1. The forecast fixture must have one entry.
        one_day_payload = {
            "daily": {
                "time": ["2026-05-04"],
                "temperature_2m_max": [82],
                "temperature_2m_min": [68],
                "weather_code": [2],
                "precipitation_probability_max": [20],
            }
        }
        respx.get(FORECAST_URL).respond(json=one_day_payload)
        out = await get_forecast(http_client, "Jupiter, FL", -3)
        assert out.startswith(
            "I can only forecast at least 1 day out, so here is the 1 day forecast for Jupiter, Florida."
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_uses_clamped_value_in_forecast_request(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        forecast_route = respx.get(FORECAST_URL).respond(json=fixture("forecast_jupiter_10day"))
        await get_forecast(http_client, "Jupiter, FL", 30)
        params = forecast_route.calls.last.request.url.params
        assert params["forecast_days"] == "14"

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_input_prose(self, http_client) -> None:
        out = await get_forecast(http_client, "", 3)
        assert out == "I need a city name to look up the weather."

    @respx.mock
    @pytest.mark.asyncio
    async def test_disambiguation(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_springfield"))
        out = await get_forecast(http_client, "Springfield", 3)
        assert out.startswith("There are several places called Springfield.")

    @respx.mock
    @pytest.mark.asyncio
    async def test_weather_error(self, http_client, fixture) -> None:
        respx.get(GEOCODE_URL).respond(json=fixture("geocode_jupiter_fl"))
        respx.get(FORECAST_URL).respond(status_code=500)
        out = await get_forecast(http_client, "Jupiter, FL", 3)
        assert out == (
            "I found Jupiter, Florida, but I had trouble getting the weather for it. "
            "Please try again in a moment."
        )
