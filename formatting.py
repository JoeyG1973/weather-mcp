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
