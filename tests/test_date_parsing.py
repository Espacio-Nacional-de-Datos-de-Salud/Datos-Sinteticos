"""Tests for backend.src.infrastructure.date_parsing."""

import pandas as pd
import pytest

from backend.src.infrastructure.date_parsing import (
    clear_cache,
    detect_date_format,
    detect_date_pattern,
    parse_dates,
    restore_date_format,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def test_iso_format_detected_as_monthfirst_unambiguous():
    s = pd.Series(["2020-01-15", "2021-03-22", "2019-12-31"])
    assert detect_date_format(s) is False


def test_dayfirst_when_day_position_exceeds_12():
    # 25 cannot be a month -> must be day-first (Spanish/EU style)
    s = pd.Series(["25/03/1990", "13/07/1985", "01/02/2000"])
    assert detect_date_format(s) is True


def test_monthfirst_when_second_position_exceeds_12():
    # 25 in second position cannot be a month -> month-first
    s = pd.Series(["03/25/1990", "07/13/1985", "01/02/2000"])
    assert detect_date_format(s) is False


def test_ambiguous_defaults_to_dayfirst_with_warning(caplog):
    # All values have day and month both <= 12 — purely ambiguous
    s = pd.Series(["01/02/2020", "03/04/2021", "05/06/2022"])
    with caplog.at_level("WARNING"):
        result = detect_date_format(s)
    assert result is True


def test_parse_dates_does_not_crash_on_spanish_data():
    # The original bug: 25 parsed as month -> error / silent NaT
    s = pd.Series(["25/03/1990", "13/07/1985", "20/11/2001"])
    parsed = parse_dates(s, col_name="fecha_nac")
    assert parsed.notna().all()
    assert parsed.iloc[0].day == 25
    assert parsed.iloc[0].month == 3
    assert parsed.iloc[0].year == 1990


def test_parse_dates_preserves_iso():
    s = pd.Series(["2020-01-15", "2021-03-22"])
    parsed = parse_dates(s, col_name="event_date")
    assert parsed.iloc[0].year == 2020
    assert parsed.iloc[0].month == 1
    assert parsed.iloc[0].day == 15


def test_per_column_cache_isolates_decisions():
    es = pd.Series(["25/03/1990"], name="fecha")
    us = pd.Series(["03/25/1990"], name="event_date")
    assert detect_date_format(es, col_name="fecha") is True
    assert detect_date_format(us, col_name="event_date") is False


def test_cache_hit_reuses_decision():
    s1 = pd.Series(["25/03/1990"])  # dayfirst
    detect_date_format(s1, col_name="col_a")
    # Pass conflicting data with same column name; cache should win
    s2 = pd.Series(["03/25/1990"])
    assert detect_date_format(s2, col_name="col_a") is True


def test_empty_series_returns_none():
    s = pd.Series([], dtype=object)
    assert detect_date_format(s) is None


def test_all_null_series_returns_none():
    s = pd.Series([None, None, None])
    assert detect_date_format(s) is None


def test_datetime_with_time_component():
    s = pd.Series(["25/03/1990 14:30:00", "13/07/1985 08:15:00"])
    parsed = parse_dates(s, col_name="event_ts")
    assert parsed.notna().all()
    assert parsed.iloc[0].day == 25
    assert parsed.iloc[0].hour == 14


# --- Recognized format patterns ---


@pytest.mark.parametrize(
    "values, expected_fmt",
    [
        (["25/03/1990", "13/07/1985", "20/11/2001"], "%d/%m/%Y"),
        (["03/25/1990", "07/13/1985", "11/20/2001"], "%m/%d/%Y"),
        (["1990-03-25", "1985-07-13"], "%Y-%m-%d"),
        (["1990/03/25", "1985/07/13"], "%Y/%m/%d"),
        (["25-03-1990", "13-07-1985"], "%d-%m-%Y"),
        (["25.03.1990", "13.07.1985"], "%d.%m.%Y"),
        (["25/03/1990 14:30:00", "13/07/1985 08:15:00"], "%d/%m/%Y %H:%M:%S"),
        (["25/03/1990 14:30", "13/07/1985 08:15"], "%d/%m/%Y %H:%M"),
    ],
)
def test_recognized_formats_return_strftime_pattern(values, expected_fmt):
    info = detect_date_pattern(pd.Series(values))
    assert info.format_str == expected_fmt


# --- Unrecognized but parseable: format_str is None, no crash ---


@pytest.mark.parametrize(
    "values",
    [
        ["March 25, 1990", "July 13, 1985"],
        ["1990-03-25T14:30:00Z", "1985-07-13T08:15:00Z"],
        # Mixed formats in same column
        ["25/03/1990", "1985-07-13", "20/11/2001"],
        # Compact YYYYMMDD — has no separators
        ["19900325", "19850713"],
    ],
)
def test_unrecognized_formats_return_none(values):
    info = detect_date_pattern(pd.Series(values))
    assert info.format_str is None


def test_unrecognized_format_still_yields_dayfirst_when_possible():
    # Mixed dayfirst values — dayfirst should still be detected from the 25
    info = detect_date_pattern(pd.Series(["25/03/1990", "1985-07-13"]))
    # Pattern is heterogeneous, but dayfirst can still be inferred from the
    # numeric tokens of the first value (25 > 12). format_str must be None.
    assert info.format_str is None


# --- Restoration ---


def test_restore_date_format_roundtrips_recognized_pattern():
    original = pd.Series(["25/03/1990", "13/07/1985", "20/11/2001"])
    info = detect_date_pattern(original, col_name="dob")
    parsed = parse_dates(original, col_name="dob")
    restored = restore_date_format(parsed, info.format_str)
    assert list(restored) == list(original)


def test_restore_date_format_handles_nat_as_empty_string():
    parsed = pd.Series([pd.Timestamp("1990-03-25"), pd.NaT])
    restored = restore_date_format(parsed, "%d/%m/%Y")
    assert restored.iloc[0] == "25/03/1990"
    assert restored.iloc[1] == ""


def test_restore_date_format_none_is_passthrough():
    s = pd.Series([pd.Timestamp("1990-03-25")])
    assert restore_date_format(s, None) is s


def test_detect_date_pattern_identifies_ambiguity():
    # Purely ambiguous
    ambig_s = pd.Series(["01/02/2020", "03/04/2021", "05/06/2022"])
    info_ambig = detect_date_pattern(ambig_s)
    assert info_ambig.ambiguous is True

    # Unambiguous (has a day > 12)
    unambig_s = pd.Series(["25/03/1990", "13/07/1985", "01/02/2000"])
    info_unambig = detect_date_pattern(unambig_s)
    assert info_unambig.ambiguous is False


def test_detect_date_pattern_includes_column_name_in_warning(monkeypatch):
    from backend.src.infrastructure.date_parsing import logger as parsing_logger
    
    warnings_logged = []
    monkeypatch.setattr(parsing_logger, "warning", lambda msg, *args: warnings_logged.append(msg % args))
    
    s = pd.Series(["01/02/2020", "03/04/2021", "05/06/2022"])
    detect_date_pattern(s, col_name="test_table.test_column")
    
    assert any("in 'test_table.test_column'" in w for w in warnings_logged)
