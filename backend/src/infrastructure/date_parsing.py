"""Locale-aware date format detection, parsing, and textual restoration.

Many real-world datasets (especially Spanish ones) use DD/MM/YYYY rather than
the US-default MM/DD/YYYY. Calling pd.to_datetime without dayfirst silently
flips day/month for ambiguous values and crashes when a day > 12 appears in
the day position.

Detect format once per column (cached) and use parse_dates() everywhere
instead of pd.to_datetime so callsites stay locale-agnostic. When we can
identify the exact strftime pattern, the format is stored so synthetic
output can be reformatted to match the original textual layout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import Lock

import pandas as pd

from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)

_ISO_RE = re.compile(r"^\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")
_TWO_GROUPS_RE = re.compile(r"^\D*(\d+)\D+(\d+)")
# Captures: g1, sep1, g2, sep2, g3, hh, mm, ss (time optional)
_FULL_DATE_RE = re.compile(
    r"^\s*(\d+)([-/.])(\d+)([-/.])(\d+)"
    r"(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?"
    r"\s*$"
)

_SAMPLE_SIZE = 1000
_HOMOGENEITY_THRESHOLD = 0.95


@dataclass(frozen=True)
class DateFormatInfo:
    """Detected per-column date format info.

    dayfirst is the parser hint; format_str is the strftime pattern used to
    restore the original textual layout (None when the column parses as a
    datetime but doesn't match any recognized pattern).
    """

    dayfirst: bool | None
    format_str: str | None


_cache: dict[str, DateFormatInfo] = {}
_cache_lock = Lock()


def _coerce_str_sample(series: pd.Series) -> pd.Series:
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    if len(s) > _SAMPLE_SIZE:
        s = s.sample(_SAMPLE_SIZE, random_state=0)
    return s


def _decide_dayfirst(sample: pd.Series) -> bool | None:
    if sample.str.match(_ISO_RE).all():
        return False

    extracted = sample.str.extract(_TWO_GROUPS_RE)
    if extracted.isna().any().any():
        return _ambiguous_fallback(sample)

    g0 = pd.to_numeric(extracted[0], errors="coerce")
    g1 = pd.to_numeric(extracted[1], errors="coerce")

    g0_over_12 = (g0 > 12).any()
    g1_over_12 = (g1 > 12).any()
    if g0_over_12 and not g1_over_12:
        return True
    if g1_over_12 and not g0_over_12:
        return False

    return _ambiguous_fallback(sample)


def _ambiguous_fallback(sample: pd.Series) -> bool | None:
    rate_mf = pd.to_datetime(sample, errors="coerce", dayfirst=False).notna().mean()
    rate_df = pd.to_datetime(sample, errors="coerce", dayfirst=True).notna().mean()
    if rate_df > rate_mf:
        return True
    if rate_mf > rate_df:
        return False
    if rate_mf == 0:
        return None
    logger.warning(
        "Date format ambiguous (both DD/MM and MM/DD parse at %.0f%%). "
        "Defaulting to dayfirst=True. Provide format explicitly to override.",
        rate_df * 100,
    )
    return True


def _derive_format_str(sample: pd.Series, dayfirst: bool | None) -> str | None:
    """Build a strftime pattern when the sample is homogeneous and recognized.

    Returns None if dayfirst is unknown, separators/group widths vary across
    rows, no 4-digit year is present, or the time portion is inconsistent.
    """
    if dayfirst is None:
        return None

    extracted = sample.str.extract(_FULL_DATE_RE)
    matches = extracted[0].notna()
    if matches.mean() < _HOMOGENEITY_THRESHOLD:
        return None
    extracted = extracted[matches]

    g1, sep1, g2, sep2, g3 = (extracted[i] for i in range(5))
    if g1.str.len().nunique() != 1 or g2.str.len().nunique() != 1 or g3.str.len().nunique() != 1:
        return None
    if sep1.nunique() != 1 or sep2.nunique() != 1:
        return None

    g1_l, g2_l, g3_l = len(g1.iloc[0]), len(g2.iloc[0]), len(g3.iloc[0])
    s1, s2 = sep1.iloc[0], sep2.iloc[0]

    if g1_l == 4 and g3_l != 4:
        date_fmt = f"%Y{s1}%m{s2}%d"
    elif g3_l == 4 and g1_l != 4:
        date_fmt = f"%d{s1}%m{s2}%Y" if dayfirst else f"%m{s1}%d{s2}%Y"
    else:
        return None

    hh, mm, ss = extracted[5], extracted[6], extracted[7]
    has_time_row = hh.notna()
    if has_time_row.any():
        if not has_time_row.all():
            return None
        if ss.notna().all():
            return f"{date_fmt} %H:%M:%S"
        if ss.isna().all():
            return f"{date_fmt} %H:%M"
        return None
    return date_fmt


def _detect(series: pd.Series) -> DateFormatInfo:
    sample = _coerce_str_sample(series)
    if sample.empty:
        return DateFormatInfo(dayfirst=None, format_str=None)

    dayfirst = _decide_dayfirst(sample)
    fmt = _derive_format_str(sample, dayfirst)
    return DateFormatInfo(dayfirst=dayfirst, format_str=fmt)


def detect_date_pattern(series: pd.Series, col_name: str | None = None) -> DateFormatInfo:
    """Detect dayfirst + strftime pattern for a column (cached by col_name)."""
    if col_name is not None:
        with _cache_lock:
            if col_name in _cache:
                return _cache[col_name]

    info = _detect(series)

    if col_name is not None:
        with _cache_lock:
            _cache[col_name] = info
    return info


def detect_date_format(series: pd.Series, col_name: str | None = None) -> bool | None:
    """Return dayfirst-only decision; use detect_date_pattern() for full info."""
    return detect_date_pattern(series, col_name=col_name).dayfirst


def parse_dates(
    series: pd.Series,
    col_name: str | None = None,
    *,
    utc: bool = False,
    errors: str = "coerce",
) -> pd.Series:
    """Drop-in replacement for pd.to_datetime with per-column DD/MM vs MM/DD auto-detection."""
    name = col_name if col_name is not None else getattr(series, "name", None)
    dayfirst = detect_date_format(series, col_name=name if isinstance(name, str) else None)
    if dayfirst is None:
        return pd.to_datetime(series, errors=errors, utc=utc)
    return pd.to_datetime(series, errors=errors, utc=utc, dayfirst=dayfirst)


def restore_date_format(series: pd.Series, fmt: str | None) -> pd.Series:
    """Render a datetime series back to its original textual layout.

    If ``fmt`` is None the series is returned unchanged (caller decides
    whether to keep the ISO datetime or coerce to string). NaT values
    become empty strings, matching what CSV/Parquet readers usually emit.
    """
    if fmt is None:
        return series
    dt = pd.to_datetime(series, errors="coerce", utc=False)
    if getattr(dt.dt, "tz", None) is not None:
        dt = dt.dt.tz_localize(None)
    formatted = dt.dt.strftime(fmt)
    return formatted.where(dt.notna(), "")


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
