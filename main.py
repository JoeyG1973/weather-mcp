"""Weather MCP server: tool functions, lifespan, and SSE entrypoint.

This module wires the MCP tools to the Open-Meteo I/O layer and the prose
formatting layer. Server wiring (FastMCP, lifespan, run('sse')) is filled in
by a later task; this initial cut focuses on the resolution helper.
"""
from __future__ import annotations

from typing import NamedTuple

import httpx

from formatting import (
    DisambiguationCandidate,
    expand_state_abbreviation,
    format_current,
    format_disambiguation,
    format_empty_input,
    format_geocode_error,
    format_not_found,
    format_weather_error,
)
from open_meteo import GeocodeMatch, OpenMeteoError, fetch_current, geocode


class Resolved(NamedTuple):
    """A geocoded location ready for a weather lookup."""
    name: str       # spoken-back name, e.g. 'Jupiter, Florida'
    latitude: float
    longitude: float


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
    try:
        matches = await geocode(client, query)
    except OpenMeteoError:
        return GeocodeFailed(spoken=format_geocode_error())

    if not matches:
        return NotFound(spoken=format_not_found(query))

    city, qualifier = _split_query(query)

    if qualifier:
        qualified = [m for m in matches if _qualifier_matches(m, qualifier)]
        if len(qualified) == 1:
            m = qualified[0]
            return Resolved(name=_resolved_name(m), latitude=m.latitude, longitude=m.longitude)
        if len(qualified) > 1:
            best = max(qualified, key=lambda m: m.population)
            return Resolved(name=_resolved_name(best), latitude=best.latitude, longitude=best.longitude)
        # Qualifier didn't match anything — disambiguate against the original list.
        candidates = [_to_candidate(m) for m in _top_three_by_population(matches)]
        return Disambiguation(spoken=format_disambiguation(query=city, qualifier=qualifier, candidates=candidates))

    # Unqualified query.
    if len(matches) == 1:
        m = matches[0]
        return Resolved(name=_resolved_name(m), latitude=m.latitude, longitude=m.longitude)
    candidates = [_to_candidate(m) for m in _top_three_by_population(matches)]
    return Disambiguation(spoken=format_disambiguation(query=city, qualifier=None, candidates=candidates))


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

    return format_current(payload, result.name)
