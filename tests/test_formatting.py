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


from formatting import format_forecast


class TestFormatForecast:
    def test_three_day_forecast_full_phrasing(self, fixture) -> None:
        payload = fixture("forecast_jupiter_3day")
        out = format_forecast(payload, "Jupiter, Florida", clamped_from=None)
        # 2026-05-04 is a Monday. Day 1 is "Tomorrow"; day 2 is "Tuesday"; day 3 is "Wednesday".
        assert out == (
            "Here is the 3 day forecast for Jupiter, Florida. "
            "Tomorrow, partly cloudy skies with a high of 82 and a low of 68, and a 20 percent chance of rain. "
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
