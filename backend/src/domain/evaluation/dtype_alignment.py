"""Dtype alignment between real and synthetic DataFrames.

Generators like MostlyAI encode booleans as integers and may widen int to
float. Leaving these mismatches in place silently breaks every metric that
compares values directly. We treat the synthetic dtype as the reference
because it is fixed by the generator — real data is cast to match it.
"""

import pandas as pd

from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


def align_dtypes(real: pd.DataFrame, syn: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cast real columns to match synthetic dtypes where they diverge.

    Rules per column (only applied when dtypes differ):
    - bool real, numeric syn  → cast real to int.
    - int real, float syn     → cast real to float.
    - anything else that differs → cast real to syn dtype; warn on failure.
    """
    real = real.copy()
    for col in real.columns:
        if col not in syn.columns:
            continue
        r_dtype = real[col].dtype
        s_dtype = syn[col].dtype
        if r_dtype == s_dtype:
            continue
        try:
            if pd.api.types.is_bool_dtype(r_dtype) and pd.api.types.is_numeric_dtype(s_dtype):
                real[col] = real[col].astype(int)
            elif pd.api.types.is_integer_dtype(r_dtype) and pd.api.types.is_float_dtype(s_dtype):
                real[col] = real[col].astype(float)
            else:
                real[col] = real[col].astype(s_dtype)
        except (ValueError, TypeError):
            logger.warning(
                "Could not align dtype of column '%s' from %s to %s — leaving as-is.",
                col,
                r_dtype,
                s_dtype,
            )
    return real, syn
