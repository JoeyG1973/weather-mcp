"""Async I/O wrappers around Open-Meteo's geocoding and forecast APIs.

Pure I/O: every public function takes an httpx.AsyncClient, hits the network,
and returns parsed data. No formatting, no MCP awareness.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


class OpenMeteoError(Exception):
    """Any failure talking to Open-Meteo: network error, non-2xx response, or unparseable body."""


@dataclass(frozen=True)
class GeocodeMatch:
    """A single result from the Open-Meteo geocoder."""
    name: str
    admin1: str | None
    country: str | None
    country_code: str | None
    latitude: float
    longitude: float
    population: int


async def geocode(client: httpx.AsyncClient, query: str) -> list[GeocodeMatch]:
    """Look up `query` against the Open-Meteo geocoder.

    Returns the list of matches in the order returned by the API (ranked by relevance).
    Returns an empty list if the geocoder reports no matches.
    Raises OpenMeteoError on HTTP or transport failures.
    """
    params = {"name": query, "count": 10, "language": "en", "format": "json"}
    try:
        response = await client.get(GEOCODING_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OpenMeteoError(f"geocoding request failed: {exc}") from exc

    raw_results = data.get("results") or []
    return [
        GeocodeMatch(
            name=row["name"],
            admin1=row.get("admin1"),
            country=row.get("country"),
            country_code=row.get("country_code"),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            population=int(row.get("population") or 0),
        )
        for row in raw_results
    ]
