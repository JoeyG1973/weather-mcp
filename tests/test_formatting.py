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
        # weather_code 2 -> "partly cloudy" (no trailing 'skies' in the phrase, so suffix is added)
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
        assert "78 degrees" in out
        assert "80 degrees" in out
        assert "9 miles per hour" in out
        assert "clear skies" in out

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

    def test_rain_phrase_uses_no_suffix(self) -> None:
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
