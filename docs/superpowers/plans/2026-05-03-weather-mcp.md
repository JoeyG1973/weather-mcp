# Weather MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that wraps the Open-Meteo APIs, exposing `get_current_weather` and `get_forecast` tools over SSE on `0.0.0.0:8001` for use by a voice assistant. All outputs are TTS-friendly prose with strict no-symbols rules.

**Architecture:** Three flat modules at the project root. `open_meteo.py` is pure async I/O against Open-Meteo. `formatting.py` is pure functions that turn API payloads into spoken-word prose. `main.py` wires the FastMCP server, owns the shared `httpx.AsyncClient` via FastMCP's lifespan, holds a small `_resolve_location` helper that orchestrates geocoding + disambiguation, and runs the SSE server via `mcp.run("sse")`.

**Tech Stack:** Python 3.13, `mcp>=1.27.0` (FastMCP + SSE transport), `httpx>=0.28.1`, `uv` for envs/deps, `pytest` + `pytest-asyncio` + `respx` for tests. Open-Meteo geocoding API at `https://geocoding-api.open-meteo.com` and forecast API at `https://api.open-meteo.com`.

**Spec:** `docs/superpowers/specs/2026-05-03-weather-mcp-design.md` is the source of truth. If anything in this plan contradicts the spec, the spec wins — flag the conflict and stop.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | modify | Add `pytest`, `pytest-asyncio`, `respx` to a `[dependency-groups.dev]` table. |
| `formatting.py` | create | Pure functions. WMO code map, ordinal helper, US state abbreviation dict, `format_current`, `format_forecast`, `format_disambiguation`, `format_not_found`, `format_geocode_error`, `format_weather_error`, `format_empty_input`. |
| `open_meteo.py` | create | Async I/O. `GeocodeMatch` dataclass, `OpenMeteoError`, `geocode`, `fetch_current`, `fetch_forecast`. Pure I/O — no formatting, no MCP awareness. |
| `main.py` | rewrite | FastMCP server, lifespan that owns `httpx.AsyncClient`, `_resolve_location` helper, two tool functions, `mcp.run("sse")`. |
| `tests/__init__.py` | create | Empty (pytest discovery). |
| `tests/conftest.py` | create | Shared fixtures: httpx client, fixture-loader for JSON files, current date freezing helper. |
| `tests/fixtures/geocode_jupiter_fl.json` | create | Geocoder response for "Jupiter, FL" — multiple results across states. |
| `tests/fixtures/geocode_springfield.json` | create | Geocoder response for "Springfield" — many matches across states. |
| `tests/fixtures/geocode_jupiter_only_florida.json` | create | Geocoder response for "Jupiter" with single Florida match (population tiebreaker fixture). |
| `tests/fixtures/geocode_empty.json` | create | Geocoder response with no `results` key. |
| `tests/fixtures/current_jupiter.json` | create | `/v1/forecast?current=...` response. |
| `tests/fixtures/forecast_jupiter_3day.json` | create | `/v1/forecast?daily=...&forecast_days=3` response. |
| `tests/fixtures/forecast_jupiter_10day.json` | create | 10-day daily forecast (exercises terse/full crossover at day 8). |
| `tests/test_formatting.py` | create | Pure-function tests. Includes `test_no_markdown_or_special_chars` sweep. |
| `tests/test_open_meteo.py` | create | `respx`-mocked I/O tests. |
| `tests/test_disambiguation.py` | create | End-to-end tests of `_resolve_location` from `main.py` with mocked HTTP. |

---

## Conventions for every task

- **Working directory:** `/opt/weather-mcp` for every command unless stated otherwise.
- **Run python via `uv run`** so the project venv is used. `uv run pytest -v` for tests.
- **TDD order:** failing test → minimal implementation → green test → commit.
- **Commit messages:** Conventional Commits (`feat:`, `test:`, `chore:`, `refactor:`). One topic per commit. Body explains *why* if non-obvious.
- **No partial commits:** each task ends with green tests and a commit.
- **Python style:** type hints on every public function, dataclasses for records, `async def` for I/O, no `print()` in library code.
- **Don't add what the task doesn't need:** no logging, retries, caching, or scaffolding "for later." YAGNI.

---

## Task 1: Project setup

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

This task adds dev dependencies and the bare test scaffolding so subsequent tasks can write tests immediately. No production code yet.

- [ ] **Step 1: Update `pyproject.toml`**

Current contents are 11 lines. Replace the file with:

```toml
[project]
name = "weather-mcp"
version = "0.1.0"
description = "MCP server wrapping Open-Meteo for a voice assistant"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "httpx>=0.28.1",
    "mcp>=1.27.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Sync the dev dependencies**

Run: `uv sync --dev`
Expected: succeeds and updates `uv.lock`. The three dev packages now appear under `.venv/lib/python3.13/site-packages/`.

- [ ] **Step 3: Create `tests/__init__.py`**

Empty file. Just `touch tests/__init__.py` (or write empty content).

- [ ] **Step 4: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture by filename (without extension allowed)."""
    fname = name if name.endswith(".json") else f"{name}.json"
    return json.loads((FIXTURES_DIR / fname).read_text())


@pytest.fixture
def fixture():
    """Return the load_fixture helper as a fixture."""
    return load_fixture


@pytest.fixture
async def http_client():
    """A real httpx.AsyncClient for tests that mock at the transport layer with respx."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client
```

- [ ] **Step 5: Sanity-check pytest discovers the (empty) suite**

Run: `uv run pytest -v`
Expected: exits 5 (no tests collected) — that is fine. We just want zero errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/__init__.py tests/conftest.py
git commit -m "chore: add dev dependencies and pytest scaffolding"
```

---

## Task 2: Foundation helpers — ordinal words and US state abbreviations

**Files:**
- Create: `formatting.py`
- Create: `tests/test_formatting.py`

These are the smallest pure helpers; many later tasks depend on them. Implement and test them in isolation before any composing function uses them.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_formatting.py`:

```python
"""Tests for formatting helpers and TTS prose builders."""
from __future__ import annotations

import pytest

from formatting import (
    US_STATE_ABBREVIATIONS,
    expand_state_abbreviation,
    ordinal_word,
)


class TestOrdinalWord:
    @pytest.mark.parametrize(
        "n,expected",
        [
            (1, "first"),
            (2, "second"),
            (3, "third"),
            (4, "fourth"),
            (5, "fifth"),
            (8, "eighth"),
            (9, "ninth"),
            (10, "tenth"),
            (11, "eleventh"),
            (12, "twelfth"),
            (13, "thirteenth"),
            (14, "fourteenth"),
            (19, "nineteenth"),
            (20, "twentieth"),
            (21, "twenty-first"),
            (22, "twenty-second"),
            (23, "twenty-third"),
            (29, "twenty-ninth"),
            (30, "thirtieth"),
            (31, "thirty-first"),
        ],
    )
    def test_ordinal_word(self, n: int, expected: str) -> None:
        assert ordinal_word(n) == expected

    def test_ordinal_word_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            ordinal_word(0)
        with pytest.raises(ValueError):
            ordinal_word(32)


class TestStateAbbreviations:
    def test_table_has_all_50_states_plus_dc(self) -> None:
        assert len(US_STATE_ABBREVIATIONS) == 51

    def test_known_lookups(self) -> None:
        assert US_STATE_ABBREVIATIONS["FL"] == "Florida"
        assert US_STATE_ABBREVIATIONS["NJ"] == "New Jersey"
        assert US_STATE_ABBREVIATIONS["DC"] == "District of Columbia"

    def test_expand_case_insensitive(self) -> None:
        assert expand_state_abbreviation("fl") == "Florida"
        assert expand_state_abbreviation("Fl") == "Florida"
        assert expand_state_abbreviation("FL") == "Florida"

    def test_expand_with_whitespace(self) -> None:
        assert expand_state_abbreviation("  NJ  ") == "New Jersey"

    def test_expand_returns_none_when_not_an_abbreviation(self) -> None:
        assert expand_state_abbreviation("Florida") is None
        assert expand_state_abbreviation("ZZ") is None
        assert expand_state_abbreviation("") is None
```

- [ ] **Step 2: Run tests — expect ImportError / failures**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: all tests fail because `formatting` module does not yet exist.

- [ ] **Step 3: Implement `formatting.py` (helpers only)**

Create `formatting.py`:

```python
"""TTS-friendly prose builders for the weather MCP server.

All functions in this module are pure: input data in, string out.
Output strings are designed to be spoken aloud by a TTS engine — they contain
no markdown, no parentheses or brackets, no symbols voice engines read by name,
no unit abbreviations, no degree or percent symbols.
"""
from __future__ import annotations

US_STATE_ABBREVIATIONS: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


def expand_state_abbreviation(text: str) -> str | None:
    """Return the full state name for a US postal abbreviation, or None.

    Case-insensitive, whitespace-tolerant. Returns None for full names,
    unknown codes, or empty input.
    """
    key = text.strip().upper()
    return US_STATE_ABBREVIATIONS.get(key)


_ONES = [
    "", "first", "second", "third", "fourth", "fifth",
    "sixth", "seventh", "eighth", "ninth",
]
_TEENS = {
    10: "tenth", 11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth",
}
_TENS_ORDINAL = {20: "twentieth", 30: "thirtieth"}
_TENS_CARDINAL = {20: "twenty", 30: "thirty"}


def ordinal_word(n: int) -> str:
    """Convert an integer 1..31 to its ordinal word form (e.g., 1 -> 'first', 21 -> 'twenty-first').

    Raises ValueError for values outside 1..31 (the supported range for date-of-month phrasing).
    """
    if n < 1 or n > 31:
        raise ValueError(f"ordinal_word supports 1..31, got {n}")
    if n < 10:
        return _ONES[n]
    if n < 20:
        return _TEENS[n]
    if n in _TENS_ORDINAL:
        return _TENS_ORDINAL[n]
    tens = (n // 10) * 10
    ones = n % 10
    return f"{_TENS_CARDINAL[tens]}-{_ONES[ones]}"
```

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: all tests in `TestOrdinalWord` and `TestStateAbbreviations` pass.

- [ ] **Step 5: Commit**

```bash
git add formatting.py tests/test_formatting.py
git commit -m "feat: add ordinal-word and US state abbreviation helpers"
```

---

## Task 3: WMO weather code → spoken phrase

**Files:**
- Modify: `formatting.py`
- Modify: `tests/test_formatting.py`

The Open-Meteo current and daily endpoints return a `weather_code` integer per the WMO standard. We map those codes to short spoken phrases.

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_formatting.py`:

```python
from formatting import WMO_CODE_PHRASES, weather_code_to_phrase


class TestWmoCodePhrases:
    def test_table_covers_documented_codes(self) -> None:
        # Open-Meteo documents these WMO codes. The set is fixed; we cover all of them.
        documented = {
            0,
            1, 2, 3,
            45, 48,
            51, 53, 55,
            56, 57,
            61, 63, 65,
            66, 67,
            71, 73, 75, 77,
            80, 81, 82,
            85, 86,
            95, 96, 99,
        }
        assert documented.issubset(WMO_CODE_PHRASES.keys())

    def test_every_phrase_is_non_empty_lowercase_string(self) -> None:
        for code, phrase in WMO_CODE_PHRASES.items():
            assert isinstance(phrase, str)
            assert phrase
            assert phrase == phrase.lower()

    def test_known_phrasings(self) -> None:
        assert weather_code_to_phrase(0) == "clear skies"
        assert weather_code_to_phrase(2) == "partly cloudy"
        assert weather_code_to_phrase(61) == "light rain"
        assert weather_code_to_phrase(95) == "thunderstorms"

    def test_unknown_code_returns_generic_phrase(self) -> None:
        # Defensive: if Open-Meteo returns a code we did not catalog, do not crash.
        assert weather_code_to_phrase(999) == "unknown conditions"
```

- [ ] **Step 2: Run tests — expect ImportError on the new symbols**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: the new `TestWmoCodePhrases` tests fail because `WMO_CODE_PHRASES` and `weather_code_to_phrase` don't exist yet.

- [ ] **Step 3: Add the table and lookup function to `formatting.py`**

Append to `formatting.py`:

```python
WMO_CODE_PHRASES: dict[int, str] = {
    0: "clear skies",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "light freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "rain showers",
    81: "heavy rain showers",
    82: "violent rain showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "thunderstorms with heavy hail",
}


def weather_code_to_phrase(code: int) -> str:
    """Map a WMO weather code to a TTS-friendly phrase. Unknown codes return a generic phrase."""
    return WMO_CODE_PHRASES.get(code, "unknown conditions")
```

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: all tests in this file (helpers + WMO codes) pass.

- [ ] **Step 5: Commit**

```bash
git add formatting.py tests/test_formatting.py
git commit -m "feat: add WMO weather-code to spoken-phrase mapping"
```

---

## Task 4: `format_current`

**Files:**
- Modify: `formatting.py`
- Modify: `tests/test_formatting.py`

Builds the spoken sentence for current conditions.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_formatting.py`:

```python
from formatting import format_current


SAMPLE_CURRENT_PAYLOAD = {
    "current": {
        "temperature_2m": 78,
        "apparent_temperature": 81,
        "weather_code": 2,
        "wind_speed_10m": 9,
    }
}


class TestFormatCurrent:
    def test_basic_prose(self) -> None:
        out = format_current(SAMPLE_CURRENT_PAYLOAD, "Jupiter, Florida")
        assert out == (
            "In Jupiter, Florida, it is currently 78 degrees with partly cloudy skies. "
            "It feels like 81 degrees, with winds out around 9 miles per hour."
        )

    def test_rounds_floats(self) -> None:
        payload = {
            "current": {
                "temperature_2m": 77.6,
                "apparent_temperature": 80.4,
                "weather_code": 0,
                "wind_speed_10m": 8.9,
            }
        }
        out = format_current(payload, "East Hanover, New Jersey")
        # Open-Meteo returns floats; voice prose uses whole numbers.
        assert "78 degrees" in out
        assert "80 degrees" in out
        assert "9 miles per hour" in out
        assert "clear skies" in out

    def test_clear_skies_phrasing_uses_phrase_directly(self) -> None:
        # The phrase "clear skies" already includes the noun, so the formatter
        # should not output "with clear skies skies".
        payload = {
            "current": {
                "temperature_2m": 70,
                "apparent_temperature": 70,
                "weather_code": 0,
                "wind_speed_10m": 5,
            }
        }
        out = format_current(payload, "Jupiter, Florida")
        assert "skies skies" not in out
        assert "clear skies" in out
```

Note on the third test: the WMO phrase `"clear skies"` already includes "skies", and the template ends with `"with <phrase> skies"` only if the phrase doesn't already end in "skies"/"cloudy"/"overcast"/etc. To keep things simple, the implementation will inline the phrase as-is (no trailing "skies"). The expected sentence in the first test reflects this: `"with partly cloudy skies"` — wait, that DOES say "skies" after "partly cloudy". So the rule needs more thought.

Resolve the ambiguity now: the formatter inserts the phrase as-is, **without** appending "skies". The expected first-test string then becomes `"with partly cloudy conditions"` — but that reads worse. Better rule: append `" skies"` only when the phrase does not already end in `"skies"`. Update the first test to use a phrase that exercises the suffix logic:

Replace the first test body with:

```python
    def test_basic_prose(self) -> None:
        out = format_current(SAMPLE_CURRENT_PAYLOAD, "Jupiter, Florida")
        # weather_code 2 -> "partly cloudy" (no trailing 'skies' in the phrase, so suffix is added)
        assert out == (
            "In Jupiter, Florida, it is currently 78 degrees with partly cloudy skies. "
            "It feels like 81 degrees, with winds out around 9 miles per hour."
        )

    def test_phrase_with_skies_does_not_double_suffix(self) -> None:
        payload = {
            "current": {
                "temperature_2m": 70,
                "apparent_temperature": 70,
                "weather_code": 0,  # 'clear skies'
                "wind_speed_10m": 5,
            }
        }
        out = format_current(payload, "Jupiter, Florida")
        assert "skies skies" not in out
        assert "with clear skies." in out  # the period from end of first sentence

    def test_rain_phrase_uses_conditions_suffix(self) -> None:
        payload = {
            "current": {
                "temperature_2m": 60,
                "apparent_temperature": 58,
                "weather_code": 61,  # 'light rain'
                "wind_speed_10m": 12,
            }
        }
        out = format_current(payload, "Jupiter, Florida")
        # 'light rain' is not skies-shaped; formatter says 'with light rain' (no suffix).
        assert "with light rain." in out
        assert "rain skies" not in out
```

(Replace the original `test_clear_skies_phrasing_uses_phrase_directly` test with the two `test_phrase_with_skies_does_not_double_suffix` and `test_rain_phrase_uses_conditions_suffix` tests above.)

The implementation rule is: phrases describing the *sky state* ("clear skies", "mostly clear", "partly cloudy", "overcast") get a `" skies"` suffix when they do not already end in "skies"; phrases describing *precipitation* (rain, snow, drizzle, showers, thunderstorms, fog) are read as-is. Implement via a small set of "sky-state" codes:

- [ ] **Step 2: Run tests — expect failure**

Run: `uv run pytest tests/test_formatting.py::TestFormatCurrent -v`
Expected: tests fail — `format_current` is undefined.

- [ ] **Step 3: Implement `format_current`**

Append to `formatting.py`:

```python
# WMO codes whose phrases describe the state of the sky (no precipitation noun).
_SKY_STATE_CODES = frozenset({0, 1, 2, 3})


def _conditions_clause(weather_code: int) -> str:
    """Return the post-'with' clause for a weather code.

    Sky-state codes (clear, mostly clear, partly cloudy, overcast) get a 'skies' suffix
    unless the phrase already ends in 'skies'. Precipitation phrases stand alone.
    """
    phrase = weather_code_to_phrase(weather_code)
    if weather_code in _SKY_STATE_CODES and not phrase.endswith("skies"):
        return f"{phrase} skies"
    return phrase


def format_current(payload: dict, resolved_name: str) -> str:
    """Build the spoken sentence for current weather.

    `payload` is the Open-Meteo /v1/forecast response with `current=...` fields.
    `resolved_name` is the city/state phrase to speak back, e.g. 'Jupiter, Florida'.
    """
    cur = payload["current"]
    temp = round(cur["temperature_2m"])
    feels = round(cur["apparent_temperature"])
    wind = round(cur["wind_speed_10m"])
    code = int(cur["weather_code"])
    conditions = _conditions_clause(code)
    return (
        f"In {resolved_name}, it is currently {temp} degrees with {conditions}. "
        f"It feels like {feels} degrees, with winds out around {wind} miles per hour."
    )
```

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: every formatting test passes.

- [ ] **Step 5: Commit**

```bash
git add formatting.py tests/test_formatting.py
git commit -m "feat: add format_current TTS sentence builder"
```

---

## Task 5: `format_forecast` — full and terse phrasing, clamp prefix, weekday/date crossover

**Files:**
- Modify: `formatting.py`
- Modify: `tests/test_formatting.py`

This is the longest formatting unit. It produces a multi-sentence spoken paragraph: an optional clamp-prefix sentence, an opener naming the place and day count, then per-day entries.

Date phrasing rule (from the spec):

- Day 1 of the forecast (the *next* calendar day) is anchored as "Tomorrow".
- Days 2–7 use bare weekday names ("Monday", "Tuesday", …).
- Days 8–14 use weekday plus ordinal-day-of-month ("Sunday the eleventh", "Monday the twelfth", …).

Per-day phrasing:

- Days 1–7 (full): `<anchor>, <conditions> with a high of <max> and a low of <min>, and a <precip> percent chance of rain.`
- Days 8–14 (terse): `<anchor>, <conditions> with a high of <max> and a low of <min>.`

"Conditions" in the forecast follows the same skies-vs-precipitation rule as `format_current` (`_conditions_clause`).

Clamp prefix appears only when `clamped_from is not None`:
- If the original request was *more* than 14: `"I can only forecast up to 14 days out, so here is the 14 day forecast for {name}. "`
- If the original request was *less* than 1: `"I can only forecast at least 1 day out, so here is the 1 day forecast for {name}. "`

The opener (when no clamp) is: `"Here is the {n} day forecast for {name}. "` — singular "day" when n == 1.

`format_forecast` derives the weekday for each entry from the `daily.time` array (Open-Meteo returns ISO date strings like `"2026-05-04"`). The day-of-month integer for ordinal phrasing comes from the same date.

- [ ] **Step 1: Add the fixtures**

Create `tests/fixtures/forecast_jupiter_3day.json`:

```json
{
  "daily": {
    "time": ["2026-05-04", "2026-05-05", "2026-05-06"],
    "temperature_2m_max": [82.1, 79.4, 76.0],
    "temperature_2m_min": [68.0, 65.3, 63.0],
    "weather_code": [2, 80, 61],
    "precipitation_probability_max": [20, 60, 70]
  }
}
```

Create `tests/fixtures/forecast_jupiter_10day.json`:

```json
{
  "daily": {
    "time": [
      "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08",
      "2026-05-09", "2026-05-10", "2026-05-11", "2026-05-12", "2026-05-13"
    ],
    "temperature_2m_max": [82, 79, 76, 78, 80, 81, 83, 85, 84, 82],
    "temperature_2m_min": [68, 65, 63, 64, 66, 67, 68, 70, 69, 67],
    "weather_code": [2, 80, 61, 1, 0, 2, 3, 80, 81, 95],
    "precipitation_probability_max": [20, 60, 70, 10, 0, 15, 25, 55, 70, 80]
  }
}
```

- [ ] **Step 2: Add the failing tests**

Append to `tests/test_formatting.py`:

```python
from formatting import format_forecast


class TestFormatForecast:
    def test_three_day_forecast_full_phrasing(self, fixture) -> None:
        payload = fixture("forecast_jupiter_3day")
        out = format_forecast(payload, "Jupiter, Florida", clamped_from=None)
        # 2026-05-04 is a Monday. Day 1 is "Tomorrow"; day 2 is "Tuesday"; day 3 is "Wednesday".
        assert out == (
            "Here is the 3 day forecast for Jupiter, Florida. "
            "Tomorrow, partly cloudy with a high of 82 and a low of 68, and a 20 percent chance of rain. "
            "Tuesday, rain showers with a high of 79 and a low of 65, and a 60 percent chance of rain. "
            "Wednesday, light rain with a high of 76 and a low of 63, and a 70 percent chance of rain."
        )

    def test_one_day_forecast_uses_singular_day(self, fixture) -> None:
        payload = {
            "daily": {
                "time": ["2026-05-04"],
                "temperature_2m_max": [82],
                "temperature_2m_min": [68],
                "weather_code": [2],
                "precipitation_probability_max": [20],
            }
        }
        out = format_forecast(payload, "Jupiter, Florida", clamped_from=None)
        assert out.startswith("Here is the 1 day forecast for Jupiter, Florida. ")
        assert "Tomorrow" in out

    def test_clamp_above_14_prefix(self, fixture) -> None:
        payload = fixture("forecast_jupiter_3day")  # 3-day fixture stands in; only the prefix matters
        out = format_forecast(payload, "Jupiter, Florida", clamped_from=30)
        assert out.startswith(
            "I can only forecast up to 14 days out, so here is the 3 day forecast for Jupiter, Florida. "
        )

    def test_clamp_below_1_prefix(self, fixture) -> None:
        payload = {
            "daily": {
                "time": ["2026-05-04"],
                "temperature_2m_max": [82],
                "temperature_2m_min": [68],
                "weather_code": [2],
                "precipitation_probability_max": [20],
            }
        }
        out = format_forecast(payload, "Jupiter, Florida", clamped_from=-3)
        assert out.startswith(
            "I can only forecast at least 1 day out, so here is the 1 day forecast for Jupiter, Florida. "
        )

    def test_terse_phrasing_past_day_7(self, fixture) -> None:
        payload = fixture("forecast_jupiter_10day")
        out = format_forecast(payload, "Jupiter, Florida", clamped_from=None)
        # 2026-05-04 is Monday, so day 8 is 2026-05-11 (Monday) — speak as "Monday the eleventh".
        assert "Monday the eleventh, " in out
        assert "Tuesday the twelfth, " in out
        assert "Wednesday the thirteenth, " in out
        # Days 8-10 must NOT include 'percent chance of rain'.
        terse_segment = out.split("Monday the eleventh, ", 1)[1]
        assert "percent chance of rain" not in terse_segment
        # Days 1-7 SHOULD include 'percent chance of rain'.
        full_segment = out.split("Monday the eleventh, ")[0]
        assert "percent chance of rain" in full_segment

    def test_weekday_anchors_for_first_seven_days(self, fixture) -> None:
        payload = fixture("forecast_jupiter_10day")
        out = format_forecast(payload, "Jupiter, Florida", clamped_from=None)
        # First seven entries: Tomorrow, Tue, Wed, Thu, Fri, Sat, Sun
        assert "Tomorrow, " in out
        for weekday in ("Tuesday, ", "Wednesday, ", "Thursday, ", "Friday, ", "Saturday, ", "Sunday, "):
            assert weekday in out

    def test_rounds_temps(self, fixture) -> None:
        payload = fixture("forecast_jupiter_3day")  # has 82.1, 79.4, 76.0
        out = format_forecast(payload, "Jupiter, Florida", clamped_from=None)
        assert "high of 82" in out
        assert "high of 79" in out
        assert "high of 76" in out
```

- [ ] **Step 3: Run tests — expect failure**

Run: `uv run pytest tests/test_formatting.py::TestFormatForecast -v`
Expected: tests fail — `format_forecast` is undefined.

- [ ] **Step 4: Implement `format_forecast`**

Append to `formatting.py`:

```python
from datetime import date as _date

_WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def _day_anchor(index: int, iso_date: str) -> str:
    """Return the per-day anchor phrase for the forecast.

    index is 0-based: 0 -> 'Tomorrow', 1..6 -> bare weekday, 7+ -> '<weekday> the <ordinal>'.
    """
    if index == 0:
        return "Tomorrow"
    d = _date.fromisoformat(iso_date)
    weekday = _WEEKDAY_NAMES[d.weekday()]
    if index < 7:
        return weekday
    return f"{weekday} the {ordinal_word(d.day)}"


def _per_day_sentence(anchor: str, conditions: str, hi: int, lo: int, precip: int, terse: bool) -> str:
    base = f"{anchor}, {conditions} with a high of {hi} and a low of {lo}"
    if terse:
        return f"{base}."
    return f"{base}, and a {precip} percent chance of rain."


def format_forecast(payload: dict, resolved_name: str, clamped_from: int | None) -> str:
    """Build the spoken paragraph for an N-day daily forecast.

    `payload` is the Open-Meteo /v1/forecast response with `daily=...` fields.
    `clamped_from` is the original requested day count if it was clamped to fit
    the supported 1..14 range, otherwise None.
    """
    daily = payload["daily"]
    times: list[str] = daily["time"]
    highs: list[float] = daily["temperature_2m_max"]
    lows: list[float] = daily["temperature_2m_min"]
    codes: list[int] = daily["weather_code"]
    precips: list[int] = daily["precipitation_probability_max"]
    n = len(times)

    day_word = "day" if n == 1 else "days"

    if clamped_from is None:
        prefix = ""
    elif clamped_from > n:  # asked for more than supported, clamped down
        prefix = f"I can only forecast up to 14 days out, so here is the {n} {day_word} forecast for {resolved_name}. "
    else:  # asked for less than 1, clamped up
        prefix = f"I can only forecast at least 1 day out, so here is the {n} {day_word} forecast for {resolved_name}. "

    if prefix:
        opener = ""
    else:
        opener = f"Here is the {n} {day_word} forecast for {resolved_name}. "

    sentences: list[str] = []
    for i in range(n):
        anchor = _day_anchor(i, times[i])
        conditions = _conditions_clause(int(codes[i]))
        hi = round(highs[i])
        lo = round(lows[i])
        precip = int(precips[i])
        terse = i >= 7
        sentences.append(_per_day_sentence(anchor, conditions, hi, lo, precip, terse))

    return prefix + opener + " ".join(sentences)
```

- [ ] **Step 5: Run tests — expect green**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: all formatting tests pass.

- [ ] **Step 6: Commit**

```bash
git add formatting.py tests/test_formatting.py tests/fixtures/forecast_jupiter_3day.json tests/fixtures/forecast_jupiter_10day.json
git commit -m "feat: add format_forecast with full/terse phrasing and clamp prefix"
```

---

## Task 6: Disambiguation, not-found, and error formatters

**Files:**
- Modify: `formatting.py`
- Modify: `tests/test_formatting.py`

These short formatters are needed by the resolution helper and tool handlers in later tasks. We need a small data carrier to pass disambiguation candidates to the formatter without coupling it to `open_meteo.GeocodeMatch` (which doesn't exist yet). Use a `NamedTuple`.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_formatting.py`:

```python
from formatting import (
    DisambiguationCandidate,
    format_disambiguation,
    format_not_found,
    format_geocode_error,
    format_weather_error,
    format_empty_input,
)


class TestErrorAndDisambiguationFormatters:
    def test_disambiguation_unqualified_three_candidates(self) -> None:
        candidates = [
            DisambiguationCandidate(name="Springfield", region="Illinois"),
            DisambiguationCandidate(name="Springfield", region="Missouri"),
            DisambiguationCandidate(name="Springfield", region="Massachusetts"),
        ]
        out = format_disambiguation(query="Springfield", qualifier=None, candidates=candidates)
        assert out == (
            "There are several places called Springfield. "
            "Did you mean Springfield, Illinois. Springfield, Missouri. Or Springfield, Massachusetts."
        )

    def test_disambiguation_qualified_no_match_three_candidates(self) -> None:
        candidates = [
            DisambiguationCandidate(name="Jupiter", region="Florida"),
            DisambiguationCandidate(name="Jupiter", region="North Carolina"),
            DisambiguationCandidate(name="Jupiter", region="Texas"),
        ]
        out = format_disambiguation(query="Jupiter", qualifier="Mars", candidates=candidates)
        assert out == (
            "I could not find Jupiter in Mars. "
            "Did you mean Jupiter, Florida. Jupiter, North Carolina. Or Jupiter, Texas."
        )

    def test_disambiguation_two_candidates_uses_or_at_end(self) -> None:
        candidates = [
            DisambiguationCandidate(name="Springfield", region="Illinois"),
            DisambiguationCandidate(name="Springfield", region="Missouri"),
        ]
        out = format_disambiguation(query="Springfield", qualifier=None, candidates=candidates)
        # With only 2, still uses "X. Or Y."
        assert out.endswith("Did you mean Springfield, Illinois. Or Springfield, Missouri.")

    def test_disambiguation_qualifier_state_abbreviation_expanded(self) -> None:
        candidates = [DisambiguationCandidate(name="Jupiter", region="Florida")]
        out = format_disambiguation(query="Jupiter", qualifier="Mars", candidates=candidates)
        # Single candidate edge case: still grammatical.
        assert "Mars" in out
        assert "Jupiter, Florida" in out

    def test_format_not_found(self) -> None:
        assert format_not_found("Springfield, Mars") == (
            "I could not find a place called Springfield, Mars. Please try a different city name."
        )

    def test_format_geocode_error(self) -> None:
        assert format_geocode_error() == (
            "I had trouble looking up that location. Please try again in a moment."
        )

    def test_format_weather_error(self) -> None:
        assert format_weather_error("Jupiter, Florida") == (
            "I found Jupiter, Florida, but I had trouble getting the weather for it. "
            "Please try again in a moment."
        )

    def test_format_empty_input(self) -> None:
        assert format_empty_input() == "I need a city name to look up the weather."
```

- [ ] **Step 2: Run tests — expect failure**

Run: `uv run pytest tests/test_formatting.py::TestErrorAndDisambiguationFormatters -v`
Expected: tests fail — symbols don't exist yet.

- [ ] **Step 3: Implement the formatters**

Append to `formatting.py`:

```python
from typing import NamedTuple


class DisambiguationCandidate(NamedTuple):
    """A single 'did you mean' option, ready to read aloud as 'name, region'."""
    name: str
    region: str  # full state or country name — never an abbreviation


def _join_candidates_with_or(candidates: list[DisambiguationCandidate]) -> str:
    """Render candidates as 'A, region. B, region. Or C, region.'.

    Uses periods between candidates (not semicolons) for cleaner TTS prosody.
    The final candidate is preceded by 'Or '.
    """
    rendered = [f"{c.name}, {c.region}" for c in candidates]
    if len(rendered) == 1:
        return f"{rendered[0]}."
    head = ". ".join(rendered[:-1])
    return f"{head}. Or {rendered[-1]}."


def format_disambiguation(
    query: str,
    qualifier: str | None,
    candidates: list[DisambiguationCandidate],
) -> str:
    """Build the spoken 'did you mean' sentence."""
    body = _join_candidates_with_or(candidates)
    if qualifier:
        # Qualified query whose qualifier didn't match — surface the failure first.
        return f"I could not find {query} in {qualifier}. Did you mean {body}"
    # Unqualified query — multiple results.
    return f"There are several places called {query}. Did you mean {body}"


def format_not_found(query: str) -> str:
    return f"I could not find a place called {query}. Please try a different city name."


def format_geocode_error() -> str:
    return "I had trouble looking up that location. Please try again in a moment."


def format_weather_error(resolved_name: str) -> str:
    return (
        f"I found {resolved_name}, but I had trouble getting the weather for it. "
        f"Please try again in a moment."
    )


def format_empty_input() -> str:
    return "I need a city name to look up the weather."
```

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: every test in the file passes.

- [ ] **Step 5: Commit**

```bash
git add formatting.py tests/test_formatting.py
git commit -m "feat: add disambiguation, not-found, and error TTS formatters"
```

---

## Task 7: Forbidden-character sweep across every formatter

**Files:**
- Modify: `tests/test_formatting.py`

A single test that runs every formatter against representative inputs and asserts no output contains characters voice engines mishandle. This is the safety net for the whole formatting policy.

- [ ] **Step 1: Add the sweep test**

Append to `tests/test_formatting.py`:

```python
class TestNoForbiddenCharacters:
    """Every TTS-bound formatter must avoid markdown, brackets, and speakable symbols."""

    FORBIDDEN = set("*_#`|<>[](){}&@~^\\/=+°%;")

    def _assert_clean(self, out: str, label: str) -> None:
        bad = [c for c in self.FORBIDDEN if c in out]
        assert not bad, f"{label} contains forbidden chars {bad}: {out!r}"
        assert "\n\n" not in out, f"{label} contains blank line: {out!r}"
        # Common unit abbreviations should never appear.
        for token in (" mph", "°F", "°C"):
            assert token not in out, f"{label} contains forbidden token {token!r}: {out!r}"

    def test_format_current_clean(self, fixture) -> None:
        payload = {
            "current": {
                "temperature_2m": 78,
                "apparent_temperature": 81,
                "weather_code": 2,
                "wind_speed_10m": 9,
            }
        }
        self._assert_clean(format_current(payload, "Jupiter, Florida"), "format_current")

    def test_format_forecast_clean_3day(self, fixture) -> None:
        out = format_forecast(fixture("forecast_jupiter_3day"), "Jupiter, Florida", None)
        self._assert_clean(out, "format_forecast 3-day")

    def test_format_forecast_clean_10day(self, fixture) -> None:
        out = format_forecast(fixture("forecast_jupiter_10day"), "Jupiter, Florida", None)
        self._assert_clean(out, "format_forecast 10-day")

    def test_format_forecast_clean_clamped(self, fixture) -> None:
        out = format_forecast(fixture("forecast_jupiter_3day"), "Jupiter, Florida", clamped_from=30)
        self._assert_clean(out, "format_forecast clamped")

    def test_format_disambiguation_clean(self) -> None:
        candidates = [
            DisambiguationCandidate("Springfield", "Illinois"),
            DisambiguationCandidate("Springfield", "Missouri"),
            DisambiguationCandidate("Springfield", "Massachusetts"),
        ]
        self._assert_clean(format_disambiguation("Springfield", None, candidates), "format_disambiguation unqualified")
        self._assert_clean(format_disambiguation("Jupiter", "Mars", candidates), "format_disambiguation qualified")

    def test_format_not_found_clean(self) -> None:
        self._assert_clean(format_not_found("Springfield, Mars"), "format_not_found")

    def test_format_geocode_error_clean(self) -> None:
        self._assert_clean(format_geocode_error(), "format_geocode_error")

    def test_format_weather_error_clean(self) -> None:
        self._assert_clean(format_weather_error("Jupiter, Florida"), "format_weather_error")

    def test_format_empty_input_clean(self) -> None:
        self._assert_clean(format_empty_input(), "format_empty_input")

    def test_every_wmo_phrase_is_clean(self) -> None:
        for code, phrase in WMO_CODE_PHRASES.items():
            self._assert_clean(phrase, f"WMO_CODE_PHRASES[{code}]")
```

- [ ] **Step 2: Run tests — expect green**

Run: `uv run pytest tests/test_formatting.py -v`
Expected: every test passes. If any fail, fix the offending formatter — do not loosen the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_formatting.py
git commit -m "test: sweep every formatter for TTS-forbidden characters"
```

---

## Task 8: `open_meteo.GeocodeMatch`, `OpenMeteoError`, and `geocode`

**Files:**
- Create: `open_meteo.py`
- Create: `tests/test_open_meteo.py`
- Create: `tests/fixtures/geocode_jupiter_fl.json`
- Create: `tests/fixtures/geocode_springfield.json`
- Create: `tests/fixtures/geocode_jupiter_only_florida.json`
- Create: `tests/fixtures/geocode_empty.json`

Pure I/O wrapper around the geocoding endpoint. Returns a list of `GeocodeMatch`. Raises `OpenMeteoError` on any HTTP-layer failure or non-2xx response.

- [ ] **Step 1: Create the geocoding fixtures**

`tests/fixtures/geocode_jupiter_fl.json` — Open-Meteo returns a list of matches. We craft a multi-state set to exercise both qualifier matching and population tiebreaking:

```json
{
  "results": [
    {
      "id": 1,
      "name": "Jupiter",
      "latitude": 26.93423,
      "longitude": -80.0942,
      "country_code": "US",
      "country": "United States",
      "admin1": "Florida",
      "admin2": "Palm Beach",
      "population": 61047,
      "feature_code": "PPL"
    },
    {
      "id": 2,
      "name": "Jupiter",
      "latitude": 35.45,
      "longitude": -82.61,
      "country_code": "US",
      "country": "United States",
      "admin1": "North Carolina",
      "population": 250,
      "feature_code": "PPL"
    },
    {
      "id": 3,
      "name": "Jupiter Inlet Beach Colony",
      "latitude": 26.95,
      "longitude": -80.07,
      "country_code": "US",
      "country": "United States",
      "admin1": "Florida",
      "population": 425,
      "feature_code": "PPL"
    }
  ]
}
```

`tests/fixtures/geocode_springfield.json`:

```json
{
  "results": [
    {"id": 11, "name": "Springfield", "latitude": 39.78, "longitude": -89.65, "country_code": "US", "country": "United States", "admin1": "Illinois", "population": 116250, "feature_code": "PPL"},
    {"id": 12, "name": "Springfield", "latitude": 37.21, "longitude": -93.30, "country_code": "US", "country": "United States", "admin1": "Missouri", "population": 169176, "feature_code": "PPL"},
    {"id": 13, "name": "Springfield", "latitude": 42.10, "longitude": -72.59, "country_code": "US", "country": "United States", "admin1": "Massachusetts", "population": 153606, "feature_code": "PPL"},
    {"id": 14, "name": "Springfield", "latitude": 39.92, "longitude": -83.81, "country_code": "US", "country": "United States", "admin1": "Ohio", "population": 58662, "feature_code": "PPL"},
    {"id": 15, "name": "Springfield", "latitude": 44.05, "longitude": -123.02, "country_code": "US", "country": "United States", "admin1": "Oregon", "population": 60177, "feature_code": "PPL"}
  ]
}
```

`tests/fixtures/geocode_jupiter_only_florida.json` — used to exercise the qualified-query population tiebreaker (two matches in the same state):

```json
{
  "results": [
    {"id": 1, "name": "Jupiter", "latitude": 26.93, "longitude": -80.09, "country_code": "US", "country": "United States", "admin1": "Florida", "population": 61047, "feature_code": "PPL"},
    {"id": 3, "name": "Jupiter", "latitude": 26.95, "longitude": -80.07, "country_code": "US", "country": "United States", "admin1": "Florida", "population": 425, "feature_code": "PPL"}
  ]
}
```

`tests/fixtures/geocode_empty.json` — Open-Meteo omits the `results` key when there are zero hits:

```json
{
  "generationtime_ms": 0.123
}
```

- [ ] **Step 2: Add failing tests**

Create `tests/test_open_meteo.py`:

```python
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
```

- [ ] **Step 3: Run tests — expect failure**

Run: `uv run pytest tests/test_open_meteo.py -v`
Expected: tests fail — the `open_meteo` module does not yet exist.

- [ ] **Step 4: Implement `open_meteo.py`**

Create `open_meteo.py`:

```python
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
```

- [ ] **Step 5: Run tests — expect green**

Run: `uv run pytest tests/test_open_meteo.py -v`
Expected: all `TestGeocode` tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_meteo.py tests/test_open_meteo.py tests/fixtures/geocode_*.json
git commit -m "feat: add Open-Meteo geocoder client with parsed GeocodeMatch results"
```

---

## Task 9: `open_meteo.fetch_current` and `fetch_forecast`

**Files:**
- Modify: `open_meteo.py`
- Modify: `tests/test_open_meteo.py`
- Create: `tests/fixtures/current_jupiter.json`

The two forecast-endpoint functions hit the same URL with different `current=` / `daily=` field lists. Both share the imperial-unit query params.

- [ ] **Step 1: Create the current-weather fixture**

`tests/fixtures/current_jupiter.json`:

```json
{
  "latitude": 26.93,
  "longitude": -80.09,
  "current": {
    "time": "2026-05-03T15:00",
    "temperature_2m": 78.4,
    "apparent_temperature": 81.0,
    "weather_code": 2,
    "wind_speed_10m": 9.2
  },
  "current_units": {
    "temperature_2m": "°F",
    "apparent_temperature": "°F",
    "wind_speed_10m": "mph"
  }
}
```

- [ ] **Step 2: Add failing tests**

Append to `tests/test_open_meteo.py`:

```python
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
```

- [ ] **Step 3: Run tests — expect failure**

Run: `uv run pytest tests/test_open_meteo.py -v`
Expected: the new tests fail — `fetch_current` and `fetch_forecast` are undefined.

- [ ] **Step 4: Implement the fetchers**

Append to `open_meteo.py`:

```python
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_IMPERIAL_PARAMS = {
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
}

_CURRENT_FIELDS = "temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
_DAILY_FIELDS = "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max"


async def fetch_current(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """Fetch current conditions for the given coordinates. Returns the raw JSON payload."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": _CURRENT_FIELDS,
        **_IMPERIAL_PARAMS,
    }
    return await _get_forecast(client, params)


async def fetch_forecast(client: httpx.AsyncClient, lat: float, lon: float, days: int) -> dict:
    """Fetch the daily forecast for the given coordinates. Returns the raw JSON payload."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": _DAILY_FIELDS,
        "forecast_days": days,
        **_IMPERIAL_PARAMS,
    }
    return await _get_forecast(client, params)


async def _get_forecast(client: httpx.AsyncClient, params: dict) -> dict:
    try:
        response = await client.get(FORECAST_URL, params=params)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OpenMeteoError(f"forecast request failed: {exc}") from exc
```

- [ ] **Step 5: Run tests — expect green**

Run: `uv run pytest tests/test_open_meteo.py -v`
Expected: every Open-Meteo test passes.

- [ ] **Step 6: Commit**

```bash
git add open_meteo.py tests/test_open_meteo.py tests/fixtures/current_jupiter.json
git commit -m "feat: add fetch_current and fetch_forecast Open-Meteo wrappers"
```

---

## Task 10: `_resolve_location` — disambiguation orchestration

**Files:**
- Create: `main.py` (replace existing hello-world stub)
- Create: `tests/test_disambiguation.py`

`_resolve_location` is the helper used by both tool functions. It:

1. Calls `open_meteo.geocode`.
2. Splits the input on the first comma into `(city, qualifier)` if a comma is present.
3. Applies the disambiguation rules from the spec.
4. Returns either a `Resolved` value (single match, ready to fetch weather) or `Disambiguation` (the spoken "did you mean" prose), or `NotFound` (the spoken "could not find" prose), or `GeocodeFailed` (network/HTTP error).

Tool functions then dispatch on the returned variant.

We use a small tagged union: a Python `dataclass`-based discriminated set is overkill; a `NamedTuple` per variant works, or we can return `Resolved | str` where any string is a final TTS response. **Cleanest:** return a `ResolveResult` that is one of four `NamedTuple` shapes; tool code checks `isinstance`.

This task's tests live in `tests/test_disambiguation.py` because they exercise the rule logic with mocked HTTP — separate from the formatting tests and from the I/O tests.

- [ ] **Step 1: Add the failing tests**

Create `tests/test_disambiguation.py`:

```python
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
        # Top three by population from the fixture: FL (61047), NC (250), Inlet Beach Colony FL (425).
        # Sorted by pop descending: FL 61047, Inlet Beach Colony FL 425, NC 250.
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `uv run pytest tests/test_disambiguation.py -v`
Expected: tests fail — none of the names from `main` exist yet.

- [ ] **Step 3: Implement `main.py` (resolution logic only — server wiring comes later)**

Replace `main.py`'s contents with:

```python
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
    format_disambiguation,
    format_geocode_error,
    format_not_found,
)
from open_meteo import GeocodeMatch, OpenMeteoError, geocode


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
```

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest tests/test_disambiguation.py -v`
Expected: every disambiguation test passes.

Run the full suite: `uv run pytest -v`
Expected: every test in every file passes.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_disambiguation.py
git commit -m "feat: add _resolve_location helper with disambiguation rules"
```

---

## Task 11: `get_current_weather` tool function

**Files:**
- Modify: `main.py`
- Modify: `tests/test_disambiguation.py` (or create `tests/test_tools.py` — see below)

Tool function dispatches on the resolution result. On `Resolved`, it calls `fetch_current`, then `format_current`. On any other variant, it returns the spoken prose from the variant directly. On `OpenMeteoError` from `fetch_current`, returns `format_weather_error(resolved.name)`.

We test the tool function as a plain async function (not via the MCP server) — tests construct an httpx client, mock both endpoints, and call the function directly. Create a dedicated test file for tool tests.

- [ ] **Step 1: Create `tests/test_tools.py` with failing tests**

```python
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
        out = await get_current_weather(http_client, "Springfield")
        assert out.startswith("There are several places called Springfield.")
        # Forecast endpoint must NOT have been called.
        assert not respx.routes[FORECAST_URL].called if hasattr(respx, "routes") else True

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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `uv run pytest tests/test_tools.py -v`
Expected: every test fails — `get_current_weather` is not defined yet.

- [ ] **Step 3: Implement `get_current_weather` in `main.py`**

Append to `main.py` (above any future `if __name__` block):

```python
from formatting import format_current, format_empty_input, format_weather_error
from open_meteo import fetch_current


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
```

(Merge the new imports into the existing import block at the top of `main.py` to keep imports tidy.)

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest -v`
Expected: every test in every file passes.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_tools.py
git commit -m "feat: add get_current_weather tool function"
```

---

## Task 12: `get_forecast` tool function

**Files:**
- Modify: `main.py`
- Modify: `tests/test_tools.py`

Same shape as `get_current_weather`, plus the days-clamping logic.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_tools.py`:

```python
from main import get_forecast


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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `uv run pytest tests/test_tools.py::TestGetForecast -v`
Expected: tests fail — `get_forecast` is not defined.

- [ ] **Step 3: Implement `get_forecast`**

Append to `main.py`:

```python
from formatting import format_forecast
from open_meteo import fetch_forecast

MIN_FORECAST_DAYS = 1
MAX_FORECAST_DAYS = 14


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

    return format_forecast(payload, result.name, clamped_from)
```

(Again: merge the new imports with the existing block.)

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest -v`
Expected: every test in every file passes.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_tools.py
git commit -m "feat: add get_forecast tool function with days clamp"
```

---

## Task 13: Wire the FastMCP server, lifespan, and SSE entrypoint

**Files:**
- Modify: `main.py`

The two tool functions in tasks 11 & 12 take `client` as their first parameter. FastMCP can't supply that automatically — we wrap them in `@mcp.tool()`-decorated adapters that pull the shared `httpx.AsyncClient` out of the lifespan context.

This task has no automated tests (per the spec, server wiring is verified manually). Verification steps run the server and probe it.

- [ ] **Step 1: Add the server-wiring code at the bottom of `main.py`**

Append:

```python
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from mcp.server.fastmcp import Context, FastMCP


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


def main() -> None:
    mcp.run("sse")


if __name__ == "__main__":
    main()
```

The wrapper functions are named `*_tool` so they don't shadow the inner async functions (still imported and unit-tested directly via Tasks 11–12). The MCP-visible tool names come from the explicit `name=` argument to `@mcp.tool`.

- [ ] **Step 2: Run the full unit-test suite (server wiring should not break anything)**

Run: `uv run pytest -v`
Expected: every test still passes.

- [ ] **Step 3: Start the server in the background**

Run: `uv run python main.py &`
Expected: server logs `Uvicorn running on http://0.0.0.0:8001`. Note the PID.

If you see `ImportError: cannot import name ... from 'mcp.server.fastmcp'` — verify `mcp>=1.27.0` is installed (`uv pip show mcp`). If `Context` lives at a different path in your installed version, update the import to match.

- [ ] **Step 4: Probe the SSE endpoint exists**

Run: `curl -sN -o /dev/null -w "%{http_code}\n" http://0.0.0.0:8001/sse --max-time 2 || true`
Expected: `200` (the connection stays open until you cut it; `--max-time 2` is so curl returns).

- [ ] **Step 5: List tools via the Python MCP SDK**

Run:

```bash
uv run python -c "
import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def main():
    async with sse_client('http://0.0.0.0:8001/sse') as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for t in tools.tools:
                print(t.name, '-', (t.description or '').splitlines()[0])

asyncio.run(main())
"
```

Expected output (tool order may vary):
```
get_current_weather - Get current weather conditions for a city.
get_forecast - Get a daily weather forecast for a city.
```

- [ ] **Step 6: Call `get_current_weather` end-to-end against the live API**

Run:

```bash
uv run python -c "
import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def main():
    async with sse_client('http://0.0.0.0:8001/sse') as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool('get_current_weather', {'location': 'Jupiter, FL'})
            for c in result.content:
                print(getattr(c, 'text', c))

asyncio.run(main())
"
```

Expected: a single sentence-pair starting with `In Jupiter, Florida, it is currently` followed by a temperature, conditions, feels-like, and wind. No symbols, no markdown.

- [ ] **Step 7: Call `get_forecast` end-to-end**

Run:

```bash
uv run python -c "
import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def main():
    async with sse_client('http://0.0.0.0:8001/sse') as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool('get_forecast', {'location': 'Jupiter, FL', 'days': 3})
            for c in result.content:
                print(getattr(c, 'text', c))

asyncio.run(main())
"
```

Expected: paragraph beginning `Here is the 3 day forecast for Jupiter, Florida.` followed by three day-entries.

- [ ] **Step 8: Verify clamping**

Run the same probe with `days=30`. Expected output begins with `I can only forecast up to 14 days out, so here is the 14 day forecast for Jupiter, Florida.`.

- [ ] **Step 9: Verify disambiguation**

Run the same probe with `location='Springfield'`. Expected: `There are several places called Springfield. Did you mean ...` — no forecast call should hit Open-Meteo.

- [ ] **Step 10: Stop the background server**

Run: `kill <PID>` (the PID from Step 3).
Expected: server shuts down cleanly; the lifespan exit closes the httpx client.

- [ ] **Step 11: Commit**

```bash
git add main.py
git commit -m "feat: wire FastMCP server, lifespan-managed httpx client, SSE entrypoint"
```

---

## Self-review notes (already applied)

- **Spec coverage:** every section of the spec maps to at least one task. Architecture (Tasks 1, 8, 9, 13). Tool contracts (Tasks 4–6, 11, 12). Geocoding rules (Task 10). Formatting policy (Tasks 2–7). Error handling (Tasks 8–12). Server lifecycle (Task 13). Testing (Tasks 1–12 throughout). Acceptance criteria (Task 13 manual probes).
- **Type consistency:** `GeocodeMatch` (Task 8) → `_qualifier_matches` and `_to_candidate` (Task 10) use `match.admin1`, `match.country`, `match.country_code` — names match. `DisambiguationCandidate` (Task 6) is consumed in `_to_candidate` (Task 10) — `name` and `region` fields match. `Resolved.name/latitude/longitude` (Task 10) consumed by `get_current_weather` and `get_forecast` (Tasks 11, 12) — match.
- **Placeholders:** none — every step contains the literal code or command an engineer needs.
- **Untracked scaffolding:** `main.py` already exists as the hello-world stub; Task 10 replaces its contents (and re-stages it). `pyproject.toml` exists; Task 1 rewrites it. `README.md` is empty and untouched.
