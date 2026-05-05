"""Tests for the MCP tool functions, calling them directly as async functions."""
from __future__ import annotations

import httpx
import pytest
import respx

from main import get_current_weather


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
