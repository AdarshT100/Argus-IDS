from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.core.data import load_multi_csv

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path, data: dict) -> None:
    """Write a dict-of-lists as a CSV file to path."""
    pd.DataFrame(data).to_csv(path, index=False)

# ---------------------------------------------------------------------------
# Test 1 — same schema across all files, correct concatenation
# ---------------------------------------------------------------------------

def test_same_schema_concatenation(tmp_path):
    """
    Three CSVs with identical columns should concatenate to 30 rows,
    retain all feature columns, include Label, and have a reset index.
    """
    for i in range(3):
        _write_csv(
            tmp_path / f"file_{i}.csv",
            {
                "feat_a": [float(j) for j in range(10)],
                "feat_b": [float(j) * 2 for j in range(10)],
                "feat_c": [float(j) * 3 for j in range(10)],
                "Label": ["BENIGN", "ATTACK"] * 5,
            },
        )

    result = load_multi_csv(str(tmp_path))

    assert len(result) == 30, f"Expected 30 rows, got {len(result)}"
    assert set(result.columns) == {"feat_a", "feat_b", "feat_c", "Label"}
    assert list(result.index) == list(range(30)), "Index should be reset 0-29"

# ---------------------------------------------------------------------------
# Test 2 — extra columns in one file (the DDoS scenario)
# ---------------------------------------------------------------------------

def test_extra_columns_in_one_file_are_dropped(tmp_path):
    """
    When one file has extra columns not present in others, only the
    common feature columns should appear in the result.
    """
    _write_csv(
        tmp_path / "file_a.csv",
        {
            "feat_a": [1.0, 2.0, 3.0],
            "feat_b": [4.0, 5.0, 6.0],
            "Label": ["BENIGN", "ATTACK", "BENIGN"],
        },
    )
    _write_csv(
        tmp_path / "file_b.csv",
        {
            "feat_a": [7.0, 8.0],
            "feat_b": [9.0, 10.0],
            "feat_extra": [11.0, 12.0],
            "Label": ["ATTACK", "BENIGN"],
        },
    )

    result = load_multi_csv(str(tmp_path))

    assert set(result.columns) == {"feat_a", "feat_b", "Label"}, (
        f"Extra column should be dropped. Got: {set(result.columns)}"
    )
    assert len(result) == 5, f"Expected 5 rows total, got {len(result)}"

# ---------------------------------------------------------------------------
# Test 3 — missing Label column raises ValueError
# ---------------------------------------------------------------------------

def test_missing_label_column_raises(tmp_path):
    """
    A CSV without a Label column should raise ValueError mentioning 'Label'.
    """
    _write_csv(
        tmp_path / "no_label.csv",
        {
            "feat_a": [1.0, 2.0],
            "feat_b": [3.0, 4.0],
        },
    )

    with pytest.raises(ValueError, match="Label"):
        load_multi_csv(str(tmp_path))

# ---------------------------------------------------------------------------
# Test 4 — empty directory raises FileNotFoundError
# ---------------------------------------------------------------------------

def test_empty_directory_raises(tmp_path):
    """
    Calling load_multi_csv on a directory with no CSVs should raise
    FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError):
        load_multi_csv(str(tmp_path))

# ---------------------------------------------------------------------------
# Test 5 — feature_list_override restricts output columns
# ---------------------------------------------------------------------------

def test_feature_list_override_respected(tmp_path):
    """
    When feature_list_override is provided, only those columns (plus Label)
    should appear in the result. feat_c must be excluded.
    """
    for i in range(2):
        _write_csv(
            tmp_path / f"file_{i}.csv",
            {
                "feat_a": [float(j) for j in range(5)],
                "feat_b": [float(j) * 2 for j in range(5)],
                "feat_c": [float(j) * 3 for j in range(5)],
                "Label": ["BENIGN", "ATTACK", "BENIGN", "ATTACK", "BENIGN"],
            },
        )

    result = load_multi_csv(str(tmp_path), feature_list_override=["feat_a", "feat_b"])

    assert set(result.columns) == {"feat_a", "feat_b", "Label"}, (
        f"feat_c should be excluded. Got: {set(result.columns)}"
    )
    assert len(result) == 10, f"Expected 10 rows, got {len(result)}"

# ---------------------------------------------------------------------------
# Test 6 — feature_list_override with unknown column raises ValueError
# ---------------------------------------------------------------------------

def test_feature_list_override_unknown_column_raises(tmp_path):
    """
    Passing a column in feature_list_override that doesn't exist in the
    CSVs should raise ValueError mentioning the unknown column name.
    """
    _write_csv(
        tmp_path / "file_a.csv",
        {
            "feat_a": [1.0, 2.0],
            "feat_b": [3.0, 4.0],
            "Label": ["BENIGN", "ATTACK"],
        },
    )

    with pytest.raises(ValueError, match="feat_nonexistent"):
        load_multi_csv(str(tmp_path), feature_list_override=["feat_a", "feat_nonexistent"])

# ---------------------------------------------------------------------------
# Test 7 — inf and NaN rows are dropped
# ---------------------------------------------------------------------------

def test_inf_and_nan_rows_are_dropped(tmp_path):
    """
    Rows containing inf, -inf, or NaN in any feature column must be dropped.
    Only clean rows should survive.
    """
    _write_csv(
        tmp_path / "file_with_inf.csv",
        {
            "feat_a": [1.0, np.inf, 3.0, np.nan, 5.0],
            "feat_b": [2.0, 3.0, -np.inf, 4.0, 6.0],
            "Label": ["BENIGN", "ATTACK", "BENIGN", "ATTACK", "BENIGN"],
        },
    )

    result = load_multi_csv(str(tmp_path))

    # Rows at index 1 (inf), 2 (-inf), 3 (NaN) should be dropped → 2 rows remain
    assert len(result) == 2, f"Expected 2 clean rows, got {len(result)}"
    assert not result[["feat_a", "feat_b"]].isin([np.inf, -np.inf]).any().any()
    assert not result[["feat_a", "feat_b"]].isna().any().any()