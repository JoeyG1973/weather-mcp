"""TTS-friendly prose builders for the weather MCP server.

All functions in this module are pure: input data in, string out.
Output strings are designed to be spoken aloud by a TTS engine — they contain
no markdown, no parentheses or brackets, no symbols voice engines read by name,
no unit abbreviations, no degree or percent symbols.
"""
from __future__ import annotations

from datetime import date as _date
from typing import NamedTuple

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

    day_word = "day"

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
