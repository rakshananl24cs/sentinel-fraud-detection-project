"""Chronological data loading and validation module.

This module provides a reproducible, leakage-free pipeline for loading the
credit card fraud dataset, validating schemas, and partitioning data into
chronological train, validation, and held-out test sets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Expected canonical schema definition
EXPECTED_COLUMNS: List[str] = (
    ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount", "Class"]
)
TARGET_COLUMN: str = "Class"
TIME_COLUMN: str = "Time"

# Target split counts from Master Plan specification
EXPECTED_TOTAL_ROWS: int = 284807
EXPECTED_TRAIN_ROWS: int = 199368
EXPECTED_VAL_ROWS: int = 42718
EXPECTED_TEST_ROWS: int = 42721


class DataValidationError(Exception):
    """Raised when dataset integrity or sanity checks fail."""
    pass


class SchemaValidationError(DataValidationError):
    """Raised when columns or data types do not match expectations."""
    pass


@dataclass(frozen=True)
class SplitMetadata:
    """Metadata describing chronological partition characteristics."""
    total_rows: int
    train_rows: int
    train_fraud_count: int
    train_fraud_rate: float
    val_rows: int
    val_fraud_count: int
    val_fraud_rate: float
    test_rows: int
    test_fraud_count: int
    test_fraud_rate: float
    train_last_time: float
    val_first_time: float
    val_last_time: float
    test_first_time: float
    boundary_equal_train_val: bool
    boundary_equal_val_test: bool
    cross_boundary_duplicate_count: int


@dataclass
class DatasetSplit:
    """Container holding isolated chronological feature and label partitions."""
    X_train: pd.DataFrame
    y_train: pd.Series
    X_val: pd.DataFrame
    y_val: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series
    metadata: SplitMetadata

    @property
    def feature_names(self) -> List[str]:
        """Returns ordered feature column names (excluding target Class)."""
        return list(self.X_train.columns)


class ChronologicalDataLoader:
    """Loads and chronologically partitions the fraud dataset without data leakage.

    Attributes:
        data_path: Path to the raw creditcard.csv dataset.
    """

    def __init__(self, data_path: str | Path = r"C:\data\creditcard.csv") -> None:
        self.data_path = Path(data_path)

    def load_and_validate(self) -> pd.DataFrame:
        """Loads dataset from disk in read-only mode and validates integrity.

        Returns:
            Validated pandas DataFrame.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            SchemaValidationError: If columns, types, or target labels are invalid.
            DataValidationError: If missing values or temporal inconsistencies exist.
        """
        if not self.data_path.exists():
            raise FileNotFoundError(f"Dataset not found at {self.data_path}")

        logger.info(f"Loading dataset in read-only mode from {self.data_path}")
        df = pd.read_csv(self.data_path)

        # 1. Validate Schema & Columns
        actual_cols = list(df.columns)
        if actual_cols != EXPECTED_COLUMNS:
            missing = set(EXPECTED_COLUMNS) - set(actual_cols)
            unexpected = set(actual_cols) - set(EXPECTED_COLUMNS)
            raise SchemaValidationError(
                f"Schema mismatch. Missing: {missing}, Unexpected: {unexpected}"
            )

        # 2. Validate Row Count & Completeness
        if len(df) != EXPECTED_TOTAL_ROWS:
            logger.warning(
                f"Observed row count ({len(df)}) differs from expected ({EXPECTED_TOTAL_ROWS})."
            )

        # 3. Validate Missing / Null Values
        null_counts = df.isnull().sum()
        total_nulls = int(null_counts.sum())
        if total_nulls > 0:
            cols_with_nulls = null_counts[null_counts > 0].to_dict()
            raise DataValidationError(f"Dataset contains null values: {cols_with_nulls}")

        # 4. Validate Target Labels
        unique_classes = set(df[TARGET_COLUMN].unique())
        if not unique_classes.issubset({0, 1}):
            raise SchemaValidationError(
                f"Target column '{TARGET_COLUMN}' contains unexpected labels: {unique_classes}"
            )

        # 5. Validate Temporal Monotonicity
        if not df[TIME_COLUMN].is_monotonic_increasing:
            raise DataValidationError(
                f"Feature '{TIME_COLUMN}' is not monotonically increasing. Chronological sort required."
            )

        return df

    def split(
        self,
        df: Optional[pd.DataFrame] = None,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        verify_plan_targets: bool = True,
    ) -> DatasetSplit:
        """Splits data strictly by chronological row sequence.

        Args:
            df: Optional pre-loaded dataframe. If None, loaded via load_and_validate().
            train_ratio: Proportion for training set (default 0.70).
            val_ratio: Proportion for validation set (default 0.15).
            test_ratio: Proportion for held-out test set (default 0.15).
            verify_plan_targets: If True, uses the exact master plan indices
                                (199368, 42718, 42721) to verify alignment.

        Returns:
            DatasetSplit object containing isolated splits and metadata.
        """
        if df is None:
            df = self.load_and_validate()

        n_total = len(df)

        if verify_plan_targets and n_total == EXPECTED_TOTAL_ROWS:
            train_end = EXPECTED_TRAIN_ROWS
            val_end = EXPECTED_TRAIN_ROWS + EXPECTED_VAL_ROWS
        else:
            train_end = int(n_total * train_ratio)
            val_end = train_end + int(n_total * val_ratio)

        # Chronological partitioning without shuffling
        train_df = df.iloc[:train_end]
        val_df = df.iloc[train_end:val_end]
        test_df = df.iloc[val_end:]

        # Extract features and targets
        feature_cols = [c for c in EXPECTED_COLUMNS if c != TARGET_COLUMN]
        X_train = train_df[feature_cols].copy()
        y_train = train_df[TARGET_COLUMN].copy()

        X_val = val_df[feature_cols].copy()
        y_val = val_df[TARGET_COLUMN].copy()

        X_test = test_df[feature_cols].copy()
        y_test = test_df[TARGET_COLUMN].copy()

        # Boundary checks
        t_train_last = float(train_df[TIME_COLUMN].iloc[-1])
        t_val_first = float(val_df[TIME_COLUMN].iloc[0])
        t_val_last = float(val_df[TIME_COLUMN].iloc[-1])
        t_test_first = float(test_df[TIME_COLUMN].iloc[0])

        boundary_equal_train_val = (t_train_last == t_val_first)
        boundary_equal_val_test = (t_val_last == t_test_first)

        # Cross-boundary duplicate check
        cross_dups = self._check_cross_boundary_duplicates(train_df, val_df, test_df)

        metadata = SplitMetadata(
            total_rows=n_total,
            train_rows=len(train_df),
            train_fraud_count=int(y_train.sum()),
            train_fraud_rate=float(y_train.mean()),
            val_rows=len(val_df),
            val_fraud_count=int(y_val.sum()),
            val_fraud_rate=float(y_val.mean()),
            test_rows=len(test_df),
            test_fraud_count=int(y_test.sum()),
            test_fraud_rate=float(y_test.mean()),
            train_last_time=t_train_last,
            val_first_time=t_val_first,
            val_last_time=t_val_last,
            test_first_time=t_test_first,
            boundary_equal_train_val=boundary_equal_train_val,
            boundary_equal_val_test=boundary_equal_val_test,
            cross_boundary_duplicate_count=cross_dups,
        )

        logger.info(
            f"Chronological split complete: Train={metadata.train_rows} (Fraud={metadata.train_fraud_count}), "
            f"Val={metadata.val_rows} (Fraud={metadata.val_fraud_count}), "
            f"Test={metadata.test_rows} (Fraud={metadata.test_fraud_count})"
        )

        return DatasetSplit(
            X_train=X_train,
            y_train=y_train,
            X_val=X_val,
            y_val=y_val,
            X_test=X_test,
            y_test=y_test,
            metadata=metadata,
        )

    def _check_cross_boundary_duplicates(
        self, train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame
    ) -> int:
        """Verifies whether identical feature rows cross partition boundaries."""
        # Detect rows that are duplicated across the entire dataset
        combined = pd.concat([train_df, val_df, test_df])
        dup_mask = combined.duplicated(keep=False)

        if not dup_mask.any():
            return 0

        # Extract duplicate row hashes for each partition
        train_sub = train_df[dup_mask.iloc[: len(train_df)]]
        val_sub = val_df[dup_mask.iloc[len(train_df) : len(train_df) + len(val_df)]]
        test_sub = test_df[dup_mask.iloc[len(train_df) + len(val_df) :]]

        train_hashes = set(train_sub.apply(lambda r: tuple(r), axis=1))
        val_hashes = set(val_sub.apply(lambda r: tuple(r), axis=1))
        test_hashes = set(test_sub.apply(lambda r: tuple(r), axis=1))

        cross = (
            len(train_hashes.intersection(val_hashes))
            + len(val_hashes.intersection(test_hashes))
            + len(train_hashes.intersection(test_hashes))
        )
        return cross
