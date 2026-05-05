"""Weather MCP server: tool functions, lifespan, and SSE entrypoint.

This module wires the MCP tools to the Open-Meteo I/O layer and the prose
formatting layer, then exposes them via a FastMCP SSE server. Bind host
and port are configurable; see _parse_args.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Standard-library imports
# ---------------------------------------------------------------------------
import argparse
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone as _utc
from typing import AsyncIterator, NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
import httpx
from mcp.server.fastmcp import Context, FastMCP

# ---------------------------------------------------------------------------
# First-party imports
# ---------------------------------------------------------------------------
from formatting import (
    DisambiguationCandidate,
    expand_state_abbreviation,
    format_current,
    format_disambiguation,
    format_empty_input,
    format_forecast,
    format_geocode_error,
    format_not_found,
    format_time_prefix,
    format_weather_error,
)
from open_meteo import GeocodeMatch, OpenMeteoError, fetch_current, fetch_forecast, geocode


# ---------------------------------------------------------------------------
# Location resolution types
# ---------------------------------------------------------------------------

class Resolved(NamedTuple):
    """A geocoded location ready for a weather lookup."""
    name: str       # spoken-back name, e.g. 'Jupiter, Florida'
    latitude: float
    longitude: float
    timezone: str | None  # IANA name, e.g. 'America/New_York'; None if geocoder omitted it


class Disambiguation(NamedTuple):
    """Multiple matches; spoken prose to read back."""
    spoken: str


class NotFound(NamedTuple):
    """No matches at all; spoken prose to read back."""
    spoken: str


class GeocodeFailed(NamedTuple):
    """Network/HTTP failure during geocoding; spoken prose to read back."""
    spoken: str


ResolveResult = Resolved | Disambiguation | NotFound | GeocodeFailed


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def _split_query(query: str) -> tuple[str, str | None]:
    """Split 'City, Qualifier' into (city, qualifier). Returns (query, None) if no comma."""
    if "," in query:
        city, qualifier = query.split(",", 1)
        return city.strip(), qualifier.strip()
    return query.strip(), None


def _resolved_name(match: GeocodeMatch) -> str:
    """Spoken-back name: 'name, admin1 (full)' for US, 'name, country' otherwise."""
    if match.country_code == "US" and match.admin1:
        return f"{match.name}, {match.admin1}"
    if match.country:
        return f"{match.name}, {match.country}"
    return match.name


def _qualifier_matches(match: GeocodeMatch, qualifier: str) -> bool:
    """True if the geocode result satisfies the user's qualifier (state or country)."""
    expanded = expand_state_abbreviation(qualifier)
    if expanded and match.admin1 and match.admin1.casefold() == expanded.casefold():
        return True
    if match.admin1 and match.admin1.casefold() == qualifier.casefold():
        return True
    if match.country and match.country.casefold() == qualifier.casefold():
        return True
    if match.country_code and match.country_code.casefold() == qualifier.casefold():
        return True
    return False


def _to_candidate(match: GeocodeMatch) -> DisambiguationCandidate:
    region = (
        match.admin1
        if match.country_code == "US" and match.admin1
        else (match.country or match.admin1 or "")
    )
    return DisambiguationCandidate(name=match.name, region=region)


def _top_three_by_population(matches: list[GeocodeMatch]) -> list[GeocodeMatch]:
    return sorted(matches, key=lambda m: m.population, reverse=True)[:3]


async def _resolve_location(client: httpx.AsyncClient, query: str) -> ResolveResult:
    """Resolve a free-text location query to a single Resolved match or a spoken response."""
    city, qualifier = _split_query(query)
    # Geocode on the city name only; the qualifier is resolved locally so the
    # Open-Meteo geocoding API (which takes a plain name) returns usable results.
    geocode_query = city if qualifier else query
    try:
        matches = await geocode(client, geocode_query)
    except OpenMeteoError:
        return GeocodeFailed(spoken=format_geocode_error())

    if not matches:
        return NotFound(spoken=format_not_found(query))

    if qualifier:
        qualified = [m for m in matches if _qualifier_matches(m, qualifier)]
        if len(qualified) == 1:
            return _to_resolved(qualified[0])
        if len(qualified) > 1:
            return _to_resolved(max(qualified, key=lambda m: m.population))
        # Qualifier didn't match anything — disambiguate against the original list.
        candidates = [_to_candidate(m) for m in _top_three_by_population(matches)]
        return Disambiguation(spoken=format_disambiguation(query=city, qualifier=qualifier, candidates=candidates))

    # Unqualified query.
    if len(matches) == 1:
        return _to_resolved(matches[0])
    candidates = [_to_candidate(m) for m in _top_three_by_population(matches)]
    return Disambiguation(spoken=format_disambiguation(query=city, qualifier=None, candidates=candidates))


def _to_resolved(match: GeocodeMatch) -> Resolved:
    return Resolved(
        name=_resolved_name(match),
        latitude=match.latitude,
        longitude=match.longitude,
        timezone=match.timezone,
    )


# ---------------------------------------------------------------------------
# Internal tool functions (also unit-tested directly)
# ---------------------------------------------------------------------------

MIN_FORECAST_DAYS = 1
MAX_FORECAST_DAYS = 14


def _clock(tz) -> datetime:
    """Return the current time in `tz`. Indirection so tests can pin the clock."""
    return datetime.now(tz)


def _now_in_zone(tz_name: str | None) -> tuple[datetime, bool]:
    """Resolve `tz_name` to (now, abbreviation_ok).

    On UTC fallback (None or unknown tz), abbreviation_ok is False so the prefix
    omits the abbreviation — a soft signal that the time is uncalibrated.
    """
    if tz_name:
        try:
            return _clock(ZoneInfo(tz_name)), True
        except ZoneInfoNotFoundError:
            pass
    return _clock(_utc.utc), False


def _prefix_for(tz_name: str | None) -> str:
    now, abbr_ok = _now_in_zone(tz_name)
    return format_time_prefix(now, include_abbreviation=abbr_ok)


async def get_current_weather(client: httpx.AsyncClient, location: str) -> str:
    """MCP tool body: return TTS-friendly prose describing current weather at `location`."""
    if not location or not location.strip():
        return format_empty_input()

    result = await _resolve_location(client, location)
    if not isinstance(result, Resolved):
        return result.spoken

    try:
        payload = await fetch_current(client, result.latitude, result.longitude)
    except OpenMeteoError:
        return format_weather_error(result.name)

    return f"{_prefix_for(result.timezone)} {format_current(payload, result.name)}"


async def get_forecast(client: httpx.AsyncClient, location: str, days: int) -> str:
    """MCP tool body: return TTS-friendly prose describing the daily forecast for `location`."""
    if not location or not location.strip():
        return format_empty_input()

    effective_days = max(MIN_FORECAST_DAYS, min(MAX_FORECAST_DAYS, days))
    clamped_from = days if days != effective_days else None

    result = await _resolve_location(client, location)
    if not isinstance(result, Resolved):
        return result.spoken

    try:
        payload = await fetch_forecast(client, result.latitude, result.longitude, effective_days)
    except OpenMeteoError:
        return format_weather_error(result.name)

    return f"{_prefix_for(result.timezone)} {format_forecast(payload, result.name, clamped_from)}"


# ---------------------------------------------------------------------------
# FastMCP server wiring
# ---------------------------------------------------------------------------

@dataclass
class AppState:
    """State shared across tool invocations for the lifetime of the server."""
    http: httpx.AsyncClient


@asynccontextmanager
async def lifespan(_mcp: FastMCP) -> AsyncIterator[AppState]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield AppState(http=client)


mcp = FastMCP(
    "weather-mcp",
    host="0.0.0.0",
    port=8001,
    lifespan=lifespan,
)


@mcp.tool(name="get_current_weather")
async def get_current_weather_tool(location: str, ctx: Context) -> str:
    """Get current weather conditions for a city.

    location: A city name, optionally followed by a state or country, e.g. 'Jupiter, FL'
              or 'Paris, France'. Returns a TTS-friendly prose description of current
              temperature, feels-like, sky conditions, and wind.
    """
    state: AppState = ctx.request_context.lifespan_context
    return await get_current_weather(state.http, location)


@mcp.tool(name="get_forecast")
async def get_forecast_tool(location: str, days: int, ctx: Context) -> str:
    """Get a daily weather forecast for a city.

    location: A city name, optionally followed by a state or country.
    days: Number of days to forecast, 1 to 14. Values outside this range are clamped
          and the response opens with a brief acknowledgment.
    Returns a TTS-friendly prose paragraph with one sentence per day.
    """
    state: AppState = ctx.request_context.lifespan_context
    return await get_forecast(state.http, location, days)


# ---------------------------------------------------------------------------
# CLI / environment configuration
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args; env vars supply defaults; hardcoded fallback last.

    Precedence: CLI flag > environment variable > hardcoded default.
    A non-integer WEATHER_MCP_PORT raises ValueError at startup — fail fast,
    no silent fallback.
    """
    parser = argparse.ArgumentParser(prog="weather-mcp")
    parser.add_argument(
        "--host",
        default=os.environ.get("WEATHER_MCP_HOST", "0.0.0.0"),
        help="Bind address (env: WEATHER_MCP_HOST). Default: 0.0.0.0",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WEATHER_MCP_PORT", "8001")),
        help="Bind port (env: WEATHER_MCP_PORT). Default: 8001",
    )
    return parser.parse_args(argv)


def _apply_bind_settings(mcp: FastMCP, args: argparse.Namespace) -> None:
    """Override the FastMCP instance's bind host and port from parsed args.

    FastMCP reads `settings.host` and `settings.port` at run-time inside
    `run_sse_async`, so mutating them after construction is safe. The library
    itself uses this pattern (see `settings.mount_path`).
    """
    mcp.settings.host = args.host
    mcp.settings.port = args.port


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    _apply_bind_settings(mcp, args)
    mcp.run("sse")


if __name__ == "__main__":
    main()
