# Weather MCP — Design Spec

**Date:** 2026-05-03
**Status:** Approved for implementation planning
**Audience:** Implementer of `weather-mcp`

## Goal

Build a Python MCP server that wraps the Open-Meteo APIs and exposes two tools — `get_current_weather` and `get_forecast` — for use by a voice assistant. All tool responses are TTS-friendly prose: no markdown, no bullets, no special characters. The server runs over SSE on `0.0.0.0:8001` (port chosen to avoid conflict with `sports-mcp` on 8000).

## Non-goals

- Caching of geocoding or weather results.
- Retries on HTTP failure.
- Auth, rate limiting, or per-client quotas.
- Severe-weather alerts, hourly forecasts, UV index, sunrise/sunset, precipitation amounts.
- Internationalization beyond what the upstream Open-Meteo geocoder provides.
- Tests for Starlette/SSE/Uvicorn wiring (manual verification suffices for v1).

## Architecture

Three Python modules at the project root, plus a `tests/` directory.

```
weather-mcp/
  main.py              # MCP server, tool registration, SSE/Uvicorn wiring
  open_meteo.py        # async I/O against geocoding + forecast APIs
  formatting.py        # pure functions: API payload -> TTS prose
  tests/
    conftest.py
    test_formatting.py
    test_open_meteo.py
    test_disambiguation.py
    fixtures/
      geocode_jupiter_fl.json
      geocode_springfield.json
      current_jupiter.json
      forecast_jupiter_3day.json
  pyproject.toml       # adds dev deps: pytest, pytest-asyncio, respx
  docs/superpowers/specs/2026-05-03-weather-mcp-design.md
```

### Module responsibilities

**`main.py`** — entrypoint and wiring only.
- Builds `FastMCP("weather-mcp")` and registers the two tools.
- Builds the SSE Starlette app (`mcp.sse_app()` or the equivalent in the installed `mcp` package).
- Wraps the app in a Starlette lifespan that creates `httpx.AsyncClient(timeout=5.0)` on startup, stashes it on `app.state.http`, and `aclose()`s it on shutdown.
- Tool handlers are ~5 lines each: read the client off `app.state`, call `open_meteo`, call `formatting`, return the string.
- Runs `uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")`.

**`open_meteo.py`** — async functions wrapping the HTTP APIs. Pure I/O, no formatting, no MCP awareness.
- `async def geocode(client, query) -> list[GeocodeMatch]` — calls `https://geocoding-api.open-meteo.com/v1/search` with `name=<query>`, `count=10`, `language=en`, `format=json`.
- `async def fetch_current(client, lat, lon) -> dict` — calls `https://api.open-meteo.com/v1/forecast` with `latitude`, `longitude`, `current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m`, `temperature_unit=fahrenheit`, `wind_speed_unit=mph`, `precipitation_unit=inch`.
- `async def fetch_forecast(client, lat, lon, days) -> dict` — calls the forecast endpoint with `daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max`, `forecast_days=<days>`, plus the same imperial unit params.
- `GeocodeMatch` is a dataclass: `name: str`, `admin1: str | None`, `country: str | None`, `country_code: str | None`, `latitude: float`, `longitude: float`, `population: int`.
- HTTP errors raise a single module-level exception (`OpenMeteoError`); tool handlers catch it and return the appropriate error prose.

**`formatting.py`** — pure functions; no I/O.
- `format_current(payload, resolved_name) -> str`
- `format_forecast(payload, resolved_name, clamped_from: int | None) -> str`
- `format_disambiguation(matches) -> str`
- `format_not_found(query) -> str`
- `format_geocode_error() -> str`
- `format_weather_error(resolved_name) -> str`
- `format_empty_input() -> str`
- `weather_code_to_phrase(code: int) -> str` — maps Open-Meteo WMO codes to spoken phrases.

## Tool contracts

### `get_current_weather(location: str) -> str`

1. If `location` is empty/whitespace, return `format_empty_input()`.
2. Resolve `location` per **Geocoding & disambiguation**.
3. If resolution returns disambiguation prose or "not found" prose, return that string directly.
4. Otherwise call `fetch_current(client, lat, lon)`. On `OpenMeteoError`, return `format_weather_error(resolved_name)`.
5. Return `format_current(payload, resolved_name)`.

Example output:

> "In Jupiter, Florida, it is currently 78 degrees with partly cloudy skies. It feels like 81 degrees, with winds out around 9 miles per hour."

### `get_forecast(location: str, days: int) -> str`

1. If `location` is empty/whitespace, return `format_empty_input()`.
2. Compute `effective_days = clamp(days, 1, 14)`. Track `clamped_from = days if days != effective_days else None`.
3. Resolve `location` per **Geocoding & disambiguation**.
4. If resolution returns disambiguation prose or "not found" prose, return that string directly.
5. Otherwise call `fetch_forecast(client, lat, lon, effective_days)`. On `OpenMeteoError`, return `format_weather_error(resolved_name)`.
6. Return `format_forecast(payload, resolved_name, clamped_from)`.

When `clamped_from` is set, the response opens with: *"I can only forecast up to 14 days out, so here is the 14 day forecast for Jupiter, Florida. …"* (or "1 day" / "14 days" depending on direction of clamp).

#### Date phrasing in forecast

Hybrid scheme:

- **Days 1–7** use weekday anchors. Day 1 (the next calendar day) is "Tomorrow"; days 2–7 are bare weekday names ("Monday", "Tuesday", …).
- **Days 8–14** use weekday plus date ordinal ("Sunday the eleventh", "Monday the twelfth", …) for unambiguity.

#### Per-day phrasing

- **Days 1–7, full template:** `<anchor>, <conditions> with a high of <max> and a low of <min>, and a <precip> percent chance of rain.`
- **Days 8–14, terse template:** `<anchor>, <conditions> with a high of <max> and a low of <min>.` Precipitation chance is dropped past day 7 — it is the longest field and the least reliable that far out.

Example, three-day forecast:

> "Here is the 3 day forecast for Jupiter, Florida. Tomorrow, mostly sunny with a high of 82 and a low of 68, and a 20 percent chance of rain. Monday, scattered showers with a high of 79 and a low of 65, and a 60 percent chance of rain. Tuesday, light rain with a high of 76 and a low of 63, and a 70 percent chance of rain."

## Geocoding & disambiguation

### Resolution flow

1. Call the geocoding API with the user's query.
2. If the query contains a comma, split on the first comma into `(city, qualifier)` and trim both. Otherwise `qualifier = None`.
3. Apply the rules below.

### Rules

- **Zero results from the geocoder** → return `format_not_found(query)`:
  > "I could not find a place called Springfield, Mars. Please try a different city name."

- **Qualified query** (e.g., "Jupiter, FL"):
  - Match qualifier against each result's `admin1` (full name, case-insensitive) **or** the expanded form of the qualifier via the US state-abbreviation table (e.g., "FL" → "Florida"). For non-US results, also accept matches on `country` or `country_code`.
  - **One match** → use it.
  - **Multiple matches** (e.g., a city and a township in the same state) → pick the highest-`population` result.
  - **Zero matches for the qualifier** → return `format_disambiguation(top_3_by_population)` from the original geocoder result list:
    > "I could not find Jupiter in Florida. Did you mean Jupiter, North Carolina. Jupiter, Texas. Or Jupiter, Georgia."

- **Unqualified query** (e.g., "Springfield"):
  - **One result** → use it.
  - **Multiple results** → always disambiguate. Return `format_disambiguation(top_3_by_population)`:
    > "There are several places called Springfield. Did you mean Springfield, Illinois. Springfield, Missouri. Or Springfield, Massachusetts."

### Resolved name format

Always speak the resolved name back so the listener can catch a wrong pick.

- **US results:** `"<name>, <admin1 full name>"` — e.g., "Jupiter, Florida".
- **Non-US results:** `"<name>, <country>"` — e.g., "Jupiter, France".

### US state abbreviation table

`formatting.py` (or a small `us_states.py`) holds a built-in `dict[str, str]` mapping the 50 USPS state codes plus DC to full state names. Lookup is case-insensitive. No global abbreviation table for non-US qualifiers — those must be supplied as full name or ISO country code.

## Formatting policy

These rules apply to every string returned by any formatter.

- **No markdown.** No `*`, `_`, `#`, backticks, `|`, `<`, `>`, `[`, `]`.
- **No bracketing or grouping symbols** that voice assistants read aloud as their names. Forbidden in output: `(`, `)`, `{`, `}`, `[`, `]`, `<`, `>`. Voice engines say "left parenthesis", "left curly brace", etc.
- **No other speakable symbols** in output: `&`, `@`, `~`, `^`, `\`, `/`, `=`, `+`, `_`. If a concept needs one of these, spell it out as a word ("and", "at", "slash", "plus", etc.) or restructure the sentence to avoid it.
- **No bullets, no lists.** No leading `-`, `*`, or `1.` lines. No double newlines that imply structure.
- **Numbers as digits**, except for date ordinals (see below). E.g., "78 degrees", not "seventy-eight degrees".
- **Units spelled out**: "miles per hour" (not "mph"), "degrees" (not the degree symbol), "percent" (not `%`), "inches" (not "in").
- **Date ordinals spelled out**: "May fourth" (not "May 4th"), "the eleventh" (not "the 11th").
- **State names spelled out** in spoken output: "Florida", not "FL".
- **Disambiguation list separator**: periods, not semicolons. *"Springfield, Illinois. Springfield, Missouri. Or Springfield, Massachusetts."* — periods give cleaner TTS prosody than semicolons.
- **Ordinal generation**: 1st → "first", 2nd → "second", … through 31st → "thirty-first". A small utility function in `formatting.py`.

## Error handling and networking

### HTTP client

- One shared `httpx.AsyncClient(timeout=5.0)` per process. Owned by Starlette lifespan; created on startup, `aclose()`d on shutdown.
- No retries. A single network failure surfaces immediately as a TTS error string.

### Error surfaces

All errors are returned as TTS prose strings from the tool handlers — never raised exceptions to the MCP layer.

| Failure | Response |
|---|---|
| Empty/whitespace `location` | "I need a city name to look up the weather." |
| Geocoding network/HTTP error | "I had trouble looking up that location. Please try again in a moment." |
| Geocoding returns zero results | "I could not find a place called <query>. Please try a different city name." |
| Geocoding returns ambiguous results | "Did you mean …" prose per Section 3. |
| Weather network/HTTP error | "I found <resolved name>, but I had trouble getting the weather for it. Please try again in a moment." |
| Open-Meteo returns 4xx/5xx or error JSON for weather | Same as weather network error. |
| `days` out of range | Weather is still returned, prefixed with "I can only forecast up to 14 days out, so here is the …" |

### Server lifecycle

- `main.py` builds `FastMCP("weather-mcp")`, registers the tools.
- Mounts the SSE app on Starlette via the `mcp` package's SSE helper.
- Starlette lifespan: `app.state.http = httpx.AsyncClient(timeout=5.0)` on startup, `await app.state.http.aclose()` on shutdown.
- Tool handlers reach the client through `app.state.http`.
- Run via `uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")`.

### Logging

Default Uvicorn access log only. No structured app logging in v1.

## Testing

Pytest, with `pytest-asyncio` for async tests and `respx` for mocking httpx. Add `pytest`, `pytest-asyncio`, `respx` to `pyproject.toml` as dev dependencies.

### `tests/test_formatting.py` (most important — TTS phrasing lives here)

- Happy-path tests asserting full prose strings against fixture payloads, for `format_current`, `format_forecast` (1, 3, 7, 8, 14 day variants), `format_disambiguation`, `format_not_found`, error formatters.
- **`test_no_markdown_or_special_chars`** — runs every formatter against representative payloads and asserts none of the outputs contain any of: `*`, `_`, `#`, `` ` ``, `|`, `<`, `>`, `[`, `]`, `(`, `)`, `{`, `}`, `&`, `@`, `~`, `^`, `\`, `/`, `=`, `+`, `\n\n`, `°`, `%`, or `;`. The same forbidden-character set is enforced for every formatter — these are characters voice assistants either read aloud by name or mishandle for prosody.
- **`test_no_unit_abbreviations`** — outputs do not contain `mph`, `°F`, `°C`, `in.` (as a word boundary).
- **`test_weekday_to_date_crossover`** — for a 9-day forecast, days 1–7 use weekday anchors, days 8–9 use weekday + date ordinal.
- **`test_clamp_prefix_present`** — forecast called with `clamped_from=30` produces output starting with the clamp-mention sentence.
- **`test_terse_past_day_7`** — days 8+ omit the "chance of rain" phrase.
- **`test_weather_code_to_phrase`** — table-driven; every WMO code listed in Open-Meteo's documentation maps to a non-empty string.
- **`test_ordinal_helper`** — 1 → "first", 2 → "second", 11 → "eleventh", 21 → "twenty-first", 31 → "thirty-first".

### `tests/test_open_meteo.py` (respx-mocked)

- `geocode` parses the response into `GeocodeMatch` objects with the right fields.
- `fetch_current` sends the expected query params (`latitude`, `longitude`, the `current=` field list, all three imperial unit params) and parses the response.
- `fetch_forecast` sends the expected `daily=` field list and `forecast_days=N`.
- HTTP 5xx → raises `OpenMeteoError`.
- Network error (respx simulating connect failure) → raises `OpenMeteoError`.

### `tests/test_disambiguation.py` (resolution rules end-to-end with mocked HTTP)

- Qualified query, single matching result → uses it.
- Qualified query, multiple results in the same state → tiebreaks by population.
- Qualified query, qualifier doesn't match any result → returns disambiguation prose with three candidates.
- Unqualified query, multiple results → returns disambiguation prose with three candidates.
- Zero geocoder results → returns "not found" prose.
- US state abbreviation expansion ("FL" matches `admin1 == "Florida"`).
- Non-US qualifier matched by full country name.
- Non-US qualifier matched by ISO country code.

### `tests/conftest.py`

- Fixture: `httpx.AsyncClient` for the I/O tests.
- Fixture loaders for the JSON payloads in `tests/fixtures/`.

### Out of scope for v1 tests

- Starlette/SSE/Uvicorn wiring. Manual verification (curl an SSE client, or wire to the voice assistant) is enough for the first cut.

## Open-Meteo API reference

For implementer convenience. Verify field names against the live API at implementation time.

- **Geocoding:** `GET https://geocoding-api.open-meteo.com/v1/search?name=<q>&count=10&language=en&format=json`. Response: `{"results": [{"name", "admin1", "country", "country_code", "latitude", "longitude", "population", ...}]}` (or no `results` key if empty).
- **Forecast (current):** `GET https://api.open-meteo.com/v1/forecast?latitude=<lat>&longitude=<lon>&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch`.
- **Forecast (daily):** same endpoint with `daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max&forecast_days=<n>` plus the imperial unit params.
- **WMO weather codes:** documented at <https://open-meteo.com/en/docs>. Implementer should map every documented code to a TTS-friendly phrase.

## Acceptance criteria

- `uv run python main.py` starts the server bound to `0.0.0.0:8001`.
- An MCP client connecting via SSE can list and call both tools.
- `get_current_weather("Jupiter, FL")` returns a single TTS-friendly prose string with the resolved name, current temp, feels-like, conditions, and wind.
- `get_forecast("Jupiter, FL", 3)` returns prose with three day-entries using weekday anchors.
- `get_forecast("Jupiter, FL", 30)` returns a 14-day forecast prefixed with the clamp-mention sentence.
- `get_forecast("Jupiter, FL", 10)` returns 10 day-entries with the day-8+ entries using weekday + date ordinal and omitting precipitation chance.
- `get_current_weather("Springfield")` returns disambiguation prose listing three top-population Springfields with periods between candidates.
- `get_current_weather("Jupiter, FL")` resolves to the Florida town; `get_current_weather("Jupiter, Texas")` resolves to the Texas town.
- All test files pass under `uv run pytest`.
- No formatter output contains markdown characters, parentheses, brackets, braces, other speakable symbols (`&`, `@`, `~`, `^`, `\`, `/`, `=`, `+`, `_`), unit abbreviations, the degree symbol, the percent symbol, or semicolons.
