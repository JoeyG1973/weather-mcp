# Local-time prefix for weather responses — Design Spec

**Date:** 2026-05-03
**Status:** Approved for implementation
**Audience:** Implementer of `weather-mcp` v1.1

## Goal

Prepend a one-sentence local-time context line to every successful tool response so the downstream voice assistant knows the current time of day at the queried location. Today, with no time context, the assistant says things like "rain expected this afternoon" at 11 PM.

The prefix is **context for the LLM**, not narration intended for the listener. It is delivered in the same text response (no `structuredContent` channel) so it must be valid TTS prose in case it does get read, but the assistant's system prompt is expected to absorb it without echoing.

## Example output

```
It is currently 10:25 PM EDT on Saturday. In East Hanover, New Jersey, it is currently 50 degrees with clear skies, and winds out around 5 miles per hour.
```

The first sentence is new. Everything after is the existing `format_current` output.

## Non-goals

- A separate metadata channel for the time. (Stays in the text response.)
- Prefixing disambiguation, not-found, geocode-error, weather-error, or empty-input responses. Those happen pre-geocoding (no resolved timezone) or are short error utterances where a timestamp is noise.
- New external dependencies. Uses `zoneinfo` from stdlib and the system tzdata.
- Calendar date in the prefix. Weekday alone is enough — the existing forecast formatter already uses "Tomorrow" / weekday names as date anchors.
- Timezone source other than the geocoder's `timezone` field.
- Re-fetching the timezone from the forecast API. Geocoder already returns it.

## Scope of the prefix

Applied:

- `get_current_weather` success path
- `get_forecast` success path (including the clamp-prefixed variant)

Not applied (response returned unchanged):

- Empty input
- Geocode network/HTTP error
- Not found
- Disambiguation
- Weather network/HTTP error (we *do* have a timezone here, but the error response is short and the prefix would push the actual error further down the utterance)

## Prefix format

```
It is currently <H>:<MM> <AM|PM>[ <ABBR>] on <Weekday>.
```

- **Hour:** 12-hour, no leading zero. `1`, `10`, `12`.
- **Minute:** two digits, `00`–`59`.
- **AM/PM:** uppercase, no periods.
- **Abbreviation:** the result of `datetime.tzname()` against the resolved `ZoneInfo`. Included only when it consists entirely of ASCII letters (e.g. `EDT`, `JST`, `IST`, `UTC`). If `tzname()` returns an offset string like `+09` or `-0530`, the abbreviation is omitted.
- **Weekday:** full English name from `%A` (`Sunday`, `Monday`, …).
- **Trailing period.** Single space separates the prefix from the existing weather sentence.

### Examples

- US, daylight-saving: `It is currently 10:25 PM EDT on Saturday.`
- Japan: `It is currently 11:25 AM JST on Sunday.`
- India: `It is currently 7:55 AM IST on Sunday.`
- Pyongyang (`tzname()` → `KST`): `It is currently 11:25 AM KST on Sunday.`
- A zone whose `tzname()` returns an offset like `+09`: `It is currently 11:25 AM on Sunday.` (abbreviation dropped)
- UTC fallback: `It is currently 2:25 AM on Sunday.` (no `UTC` abbreviation, per the fallback rule below)

## Timezone resolution

1. The geocoding API returns a `timezone` field per result (e.g. `"America/New_York"`, `"Asia/Tokyo"`). Parse it into `GeocodeMatch.timezone: str | None`.
2. Whichever `GeocodeMatch` resolution picks (single match, qualifier match, population tiebreak) carries its `timezone` through to a new `Resolved.timezone: str | None` field.
3. The tool handler computes `now` against that zone:
   - If `Resolved.timezone` is `None`, use UTC, and **omit the abbreviation** in the prefix.
   - If `ZoneInfo(name)` raises `ZoneInfoNotFoundError`, use UTC, and **omit the abbreviation**.
   - Otherwise use `ZoneInfo(Resolved.timezone)` and include the abbreviation if it's all letters.

The "omit abbreviation on UTC fallback" rule serves a purpose: when something failed to give us the queried location's zone, the time is less calibrated than a normal response, and dropping the abbreviation is a soft signal of that.

## Architecture changes

### `formatting.py`

New pure function:

```python
def format_time_prefix(now: datetime, *, include_abbreviation: bool = True) -> str:
    """Returns 'It is currently 10:25 PM EDT on Saturday.' style sentence.

    `now` must be timezone-aware. If `include_abbreviation` is False, or if
    now.tzname() is not all ASCII letters, the abbreviation is omitted.
    """
```

This is the only new prose function. It's pure and trivially unit-testable.

### `open_meteo.py`

`GeocodeMatch` grows one optional field:

```python
@dataclass(frozen=True)
class GeocodeMatch:
    name: str
    admin1: str | None
    country: str | None
    country_code: str | None
    latitude: float
    longitude: float
    population: int
    timezone: str | None     # NEW; from response['timezone']
```

`geocode()` parses `row.get("timezone")`.

### `main.py`

`Resolved` grows one field:

```python
class Resolved(NamedTuple):
    name: str
    latitude: float
    longitude: float
    timezone: str | None     # NEW
```

Both call sites in `_resolve_location` populate it from the chosen `GeocodeMatch`.

A small private helper:

```python
def _now_in_zone(timezone: str | None) -> tuple[datetime, bool]:
    """Returns (now, abbreviation_ok). abbreviation_ok=False on UTC fallback."""
    if timezone:
        try:
            return datetime.now(ZoneInfo(timezone)), True
        except ZoneInfoNotFoundError:
            pass
    return datetime.now(timezone_utc), False
```

(`timezone_utc` is `datetime.timezone.utc` — naming chosen to avoid shadowing the parameter.)

The tool handlers `get_current_weather` and `get_forecast` change in the same shape:

```python
now, abbr_ok = _now_in_zone(result.timezone)
prefix = format_time_prefix(now, include_abbreviation=abbr_ok)
return f"{prefix} {format_current(payload, result.name)}"
```

The handlers stay short. The only logic added is the `_now_in_zone` call and the `f"{prefix} {…}"` concat.

### Test files

- `tests/test_formatting.py` gains a `Test format_time_prefix` block: hour formatting, AM/PM, weekday, abbreviation included for letter zones, abbreviation omitted for offset zones, `include_abbreviation=False` honored.
- `tests/test_formatting.py` forbidden-char sweep is extended to include `format_time_prefix` outputs across several zones.
- `tests/test_open_meteo.py` updates the `geocode` parsing tests to assert `timezone` is populated; adds a fixture variant where `timezone` is missing to assert `None`.
- `tests/test_tools.py` gains:
  - `get_current_weather` success path: response starts with the prefix, contains `EDT` for a US fixture.
  - `get_forecast` success path: same, including the clamp variant.
  - **Tokyo case**: a Tokyo fixture produces `JST` in the prefix.
  - **Bad-timezone fallback**: a fixture with `timezone: "Not/AReal_Zone"` produces a prefix with no abbreviation.
  - **No-prefix paths**: disambiguation, not-found, geocode-error, weather-error, and empty-input responses do **not** start with `"It is currently"`.

`now` is injected into tests via `freezegun`-style monkeypatching of a single seam — see Testability below.

## Testability

The tool handlers must be deterministic for tests. Two ways we considered:

1. Inject `now` as an argument to `get_current_weather`/`get_forecast` (defaulting to `datetime.now(...)`).
2. Monkeypatch a single seam in `main.py`.

We pick **option 2**: a module-level `_clock` callable in `main.py` that defaults to `datetime.now`. Tests `monkeypatch.setattr(main, "_clock", lambda tz: fixed_dt.astimezone(tz))`. This keeps the public tool signatures unchanged and adds no `Optional[datetime]` noise to MCP tool schemas.

```python
def _clock(tz) -> datetime:
    return datetime.now(tz)

def _now_in_zone(timezone: str | None) -> tuple[datetime, bool]:
    if timezone:
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            return _clock(timezone_utc), False
        return _clock(zone), True
    return _clock(timezone_utc), False
```

## Error handling

- `ZoneInfoNotFoundError` from a malformed/missing tzdata zone → UTC fallback, no abbreviation.
- The geocoder returning no `timezone` field on a row → `GeocodeMatch.timezone is None` → UTC fallback, no abbreviation. (Open-Meteo always returns it in practice, but parsing tolerates absence.)
- The prefix code never raises into the tool handler. If `format_time_prefix` itself raised (it shouldn't), the user would lose the entire response, which is worse than no prefix. Defensive: the tool handler treats prefix composition as best-effort but, given the simple operations involved, no try/except is added in v1.

## Acceptance criteria

- `get_current_weather("East Hanover, NJ")` returns prose starting with `It is currently <time> EDT on <Weekday>. In East Hanover, New Jersey, …` (or `EST` depending on time of year).
- `get_current_weather("Tokyo")` returns prose starting with a JST prefix.
- `get_forecast("Jupiter, FL", 3)` returns prose with a `EDT`/`EST` prefix followed by the existing 3-day prose.
- `get_forecast("Jupiter, FL", 30)` returns the clamp-prefix sentence (now preceded by the time-prefix sentence).
- A geocode fixture with `timezone: null` produces a prefix without an abbreviation.
- A geocode fixture with a bogus timezone string produces a prefix without an abbreviation (UTC fallback).
- Disambiguation, not-found, geocode-error, weather-error, and empty-input responses are byte-identical to v1 — no time prefix.
- `uv run pytest` passes, including the existing forbidden-character sweep extended over `format_time_prefix`.
- `systemctl restart weather-mcp.service` succeeds and the service is `active (running)` afterward.
