"""Tests for ChronologicalDataLoader and dataset validation."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ml.src.data.loader import (
    EXPECTED_COLUMNS,
    EXPECTED_TEST_ROWS,
    EXPECTED_TOTAL_ROWS,
    EXPECTED_TRAIN_ROWS,
    EXPECTED_VAL_ROWS,
    ChronologicalDataLoader,
    DataValidationError,
    SchemaValidationError,
)


@pytest.fixture
def mock_valid_df() -> pd.DataFrame:
    """Creates a valid miniature mock DataFrame matching the dataset schema."""
    n_rows = 100
    data = {"Time": np.arange(n_rows, dtype=float)}
    for i in range(1, 29):
        data[f"V{i}"] = np.random.randn(n_rows)
    data["Amount"] = np.random.uniform(1.0, 500.0, size=n_rows)
    data["Class"] = np.random.choice([0, 1], size=n_rows, p=[0.9, 0.1])
    return pd.DataFrame(data)[EXPECTED_COLUMNS]


def test_schema_validation_missing_column(tmp_path: Path, mock_valid_df: pd.DataFrame):
    """Verifies that missing columns trigger SchemaValidationError."""
    bad_df = mock_valid_df.drop(columns=["V14"])
    csv_path = tmp_path / "bad_schema.csv"
    bad_df.to_csv(csv_path, index=False)

    loader = ChronologicalDataLoader(csv_path)
    with pytest.raises(SchemaValidationError, match="Schema mismatch"):
        loader.load_and_validate()


def test_schema_validation_unexpected_labels(tmp_path: Path, mock_valid_df: pd.DataFrame):
    """Verifies that unexpected target labels trigger SchemaValidationError."""
    bad_df = mock_valid_df.copy()
    bad_df.loc[0, "Class"] = 2  # Invalid label
    csv_path = tmp_path / "bad_labels.csv"
    bad_df.to_csv(csv_path, index=False)

    loader = ChronologicalDataLoader(csv_path)
    with pytest.raises(SchemaValidationError, match="unexpected labels"):
        loader.load_and_validate()


def test_temporal_monotonicity_rejection(tmp_path: Path, mock_valid_df: pd.DataFrame):
    """Verifies that non-monotonic Time triggers DataValidationError."""
    bad_df = mock_valid_df.copy()
    bad_df.loc[10, "Time"] = 0.0  # Out of chronological order
    csv_path = tmp_path / "bad_time.csv"
    bad_df.to_csv(csv_path, index=False)

    loader = ChronologicalDataLoader(csv_path)
    with pytest.raises(DataValidationError, match="not monotonically increasing"):
        loader.load_and_validate()


def test_null_value_rejection(tmp_path: Path, mock_valid_df: pd.DataFrame):
    """Verifies that null values trigger DataValidationError."""
    bad_df = mock_valid_df.copy()
    bad_df.loc[5, "Amount"] = np.nan
    csv_path = tmp_path / "bad_null.csv"
    bad_df.to_csv(csv_path, index=False)

    loader = ChronologicalDataLoader(csv_path)
    with pytest.raises(DataValidationError, match="contains null values"):
        loader.load_and_validate()


def test_chronological_splitting_mock(tmp_path: Path, mock_valid_df: pd.DataFrame):
    """Verifies that splitting maintains sequence order without shuffling."""
    csv_path = tmp_path / "mock.csv"
    mock_valid_df.to_csv(csv_path, index=False)

    loader = ChronologicalDataLoader(csv_path)
    split = loader.split(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, verify_plan_targets=False)

    assert len(split.X_train) == 70
    assert len(split.X_val) == 15
    assert len(split.X_test) == 15

    # Sequence order preserved
    assert list(split.X_train["Time"]) == list(range(70))
    assert list(split.X_val["Time"]) == list(range(70, 85))
    assert list(split.X_test["Time"]) == list(range(85, 100))


def test_actual_dataset_integrity_and_splits():
    """Empirically tests the actual creditcard.csv dataset against Master Plan targets."""
    loader = ChronologicalDataLoader(r"C:\data\creditcard.csv")
    split = loader.split(verify_plan_targets=True)

    meta = split.metadata

    # 1. Total and split sizes match Master Plan targets
    assert meta.total_rows == EXPECTED_TOTAL_ROWS
    assert meta.train_rows == EXPECTED_TRAIN_ROWS
    assert meta.val_rows == EXPECTED_VAL_ROWS
    assert meta.test_rows == EXPECTED_TEST_ROWS

    # 2. Fraud counts match Master Plan recorded values
    assert meta.train_fraud_count == 384
    assert meta.val_fraud_count == 56
    assert meta.test_fraud_count == 52

    # 3. Boundaries are clean (no identical timestamps spanning boundaries)
    assert meta.boundary_equal_train_val is False
    assert meta.boundary_equal_val_test is False

    # 4. Zero duplicate leakage across partition boundaries
    assert meta.cross_boundary_duplicate_count == 0

    # 5. Features and target shapes
    assert split.X_train.shape == (199368, 30)
    assert split.y_train.shape == (199368,)
    assert split.X_val.shape == (42718, 30)
    assert split.y_val.shape == (42718,)
    assert split.X_test.shape == (42721, 30)
    assert split.y_test.shape == (42721,)
    assert len(split.feature_names) == 30
    assert "Class" not in split.feature_names
