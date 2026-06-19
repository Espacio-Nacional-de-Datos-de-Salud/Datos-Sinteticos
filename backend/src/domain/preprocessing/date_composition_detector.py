"""Suggest opt-in candidates for DateCompositionRule.

A dataset that carries both a canonical date (``dob``) and split parts
(``dob_year``/``dob_month``/``dob_day``) often suffers from drift between
the two after generation — the model treats them as independent columns.
This module spots likely candidates by combining:

1. column-name heuristics (``<canonical>_year``, ``anio``, ``yr``…),
2. value coincidence on a sample (does ``year(canonical) == year_col``?).

Detection only suggests; registering the rule remains the user's call so
intentional mismatches (e.g. partial anonymisation) survive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
from backend.src.domain.encoding_types import ModelEncodingType
from backend.src.infrastructure.date_parsing import parse_dates
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


_PART_TOKENS: dict[str, tuple[str, ...]] = {
    "year": ("year", "yr", "anio", "ano", "año"),
    "month": ("month", "mon", "mes"),
    "day": ("day", "dia", "día"),
    "hour": ("hour", "hr", "hora"),
    "minute": ("minute", "min", "minuto"),
    "second": ("second", "sec", "segundo"),
}

_VALUE_COINCIDENCE_SAMPLE = 200
_VALUE_COINCIDENCE_THRESHOLD = 0.9


@dataclass(frozen=True)
class DateCompositionCandidate:
    table: str
    canonical_col: str
    part_cols: dict[str, str]
    confidence: float  # 0.0 — 1.0, fraction of sampled rows where parts match


def _tokenize(name: str) -> set[str]:
    """Split a column name into lowercase alphanumeric tokens.

    ``birth_datetime`` -> {"birth", "datetime"}; ``YearOfBirth`` -> {"year",
    "of", "birth"}; ``fecha-nac`` -> {"fecha", "nac"}.
    """
    spaced = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    return {tok for tok in re.split(r"[^a-zA-Z0-9]+", spaced.lower()) if tok}


def _name_matches_part(candidate: str, part: str) -> bool:
    """True if ``candidate``'s tokens contain at least one ``part`` keyword.

    Doesn't require the canonical column's name to overlap — that's verified
    separately by value coincidence, which is the strong signal. Name matching
    is only used to keep the candidate set small.
    """
    tokens = _tokenize(candidate)
    part_keywords = _PART_TOKENS.get(part, ())
    return any(tok in tokens for tok in part_keywords)


def _value_coincidence(canonical: pd.Series, part_series: pd.Series, part: str) -> float:
    """Fraction of rows where ``part`` extracted from canonical matches part_series."""
    parsed = parse_dates(canonical, col_name=None, log_warnings=False)
    part_numeric = pd.to_numeric(part_series, errors="coerce")
    expected = getattr(parsed.dt, part)
    both_known = parsed.notna() & part_numeric.notna()
    if not both_known.any():
        return 0.0
    sample_mask = both_known.copy()
    if sample_mask.sum() > _VALUE_COINCIDENCE_SAMPLE:
        keep = sample_mask[sample_mask].sample(_VALUE_COINCIDENCE_SAMPLE, random_state=0).index
        sample_mask = pd.Series(False, index=canonical.index)
        sample_mask.loc[keep] = True
    matches = (expected == part_numeric) & sample_mask
    return float(matches.sum()) / float(sample_mask.sum())


def detect_date_composition_candidates(
    data: dict[str, pd.DataFrame],
    encoding_types: dict[str, dict[str, str]],
) -> list[DateCompositionCandidate]:
    """Find probable canonical↔parts groupings across all tables.

    Each candidate has confidence == minimum value-coincidence over its
    detected parts; callers can threshold further (the function itself
    already requires >= _VALUE_COINCIDENCE_THRESHOLD to suggest a part).
    """
    candidates: list[DateCompositionCandidate] = []
    for table_name, types in encoding_types.items():
        df = data.get(table_name)
        if df is None:
            continue
        datetime_cols = [
            col
            for col, enc in types.items()
            if enc == ModelEncodingType.tabular_datetime and col in df.columns
        ]
        for canonical in datetime_cols:
            matched_parts: dict[str, str] = {}
            confidences: list[float] = []
            for part in _PART_TOKENS:
                for candidate_col in df.columns:
                    if candidate_col == canonical:
                        continue
                    if candidate_col in matched_parts.values():
                        continue
                    if not _name_matches_part(candidate_col, part):
                        continue
                    confidence = _value_coincidence(df[canonical], df[candidate_col], part)
                    if confidence >= _VALUE_COINCIDENCE_THRESHOLD:
                        matched_parts[part] = candidate_col
                        confidences.append(confidence)
                        break
            if matched_parts:
                candidates.append(
                    DateCompositionCandidate(
                        table=table_name,
                        canonical_col=canonical,
                        part_cols=matched_parts,
                        confidence=min(confidences),
                    )
                )
    return candidates


def build_date_composition_warnings(
    candidates: list[DateCompositionCandidate],
) -> list[dict]:
    """Render candidates as user-facing warning records (UI/metadata).

    One record per affected column (canonical + each part) so the inspection
    UI marks every linked column. They share the same ``details`` payload so
    the frontend can group them by canonical when needed.
    """
    warnings: list[dict] = []
    for cand in candidates:
        details = {
            "canonical_col": cand.canonical_col,
            "part_cols": dict(cand.part_cols),
            "confidence": cand.confidence,
            "rule_type": "date_composition",
        }
        canonical_msg = (
            f"'{cand.canonical_col}' parece estar duplicada en columnas "
            f"separadas {sorted(cand.part_cols.values())} "
            f"(coincidencia {cand.confidence:.0%}). Añade una regla "
            f"'date_composition' desde la página «Reglas de negocio» si "
            f"quieres que se deriven automáticamente; déjalo así si la "
            f"divergencia es intencionada."
        )
        warnings.append(
            {
                "table": cand.table,
                "column": cand.canonical_col,
                "kind": "date_composition_candidate",
                "default_excluded": False,
                "message": canonical_msg,
                "details": details,
            }
        )
        for part, part_col in cand.part_cols.items():
            warnings.append(
                {
                    "table": cand.table,
                    "column": part_col,
                    "kind": "date_composition_candidate",
                    "default_excluded": False,
                    "message": (
                        f"'{part_col}' coincide con el {part} de "
                        f"'{cand.canonical_col}'. Añade una regla "
                        f"'date_composition' desde la página «Reglas de "
                        f"negocio» si quieres que esta columna se derive "
                        f"automáticamente."
                    ),
                    "details": details,
                }
            )
    return warnings
