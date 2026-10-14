"""Tests for leakage-safe preprocessing and baseline model safeguards."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ml.src.preprocessing.preprocessor import FraudPreprocessor, PreprocessingError
from ml.src.models.baselines import BaselineTrainer


@pytest.fixture
def sample_feature_data():
    """Generates synthetic train and validation features."""
    np.random.seed(42)
    feature_cols = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]
    
    # Train data: mean = 10, std = 2
    X_train = pd.DataFrame(
        np.random.normal(loc=10.0, scale=2.0, size=(1000, 30)),
        columns=feature_cols
    )
    # Val data: mean = 50, std = 5 (deliberately different distribution to test leakage)
    X_val = pd.DataFrame(
        np.random.normal(loc=50.0, scale=5.0, size=(200, 30)),
        columns=feature_cols
    )
    return X_train, X_val


def test_preprocessing_leakage_safeguard(sample_feature_data):
    """Verifies scaler statistics match training data only, never validation data."""
    X_train, X_val = sample_feature_data
    preprocessor = FraudPreprocessor()
    preprocessor.fit(X_train)

    # Scaler mean must match training mean, NOT validation mean
    train_mean = X_train.values.mean(axis=0)
    scaler_mean = preprocessor.scaler.mean_
    np.testing.assert_allclose(scaler_mean, train_mean, rtol=1e-5)

    # Transform validation data
    X_val_scaled = preprocessor.transform(X_val)
    assert X_val_scaled.shape == X_val.shape
    assert list(X_val_scaled.columns) == list(X_val.columns)

    # Validation scaled data should NOT have mean zero because it was scaled with train mean
    assert not np.allclose(X_val_scaled.mean(axis=0), 0.0, atol=0.1)


def test_preprocessing_rejects_class_column(sample_feature_data):
    """Verifies that preprocessor strictly rejects inclusion of 'Class'."""
    X_train, X_val = sample_feature_data
    X_bad = X_train.copy()
    X_bad["Class"] = 0

    preprocessor = FraudPreprocessor()
    with pytest.raises(PreprocessingError, match="Target column 'Class' detected"):
        preprocessor.fit(X_bad)

    preprocessor.fit(X_train)
    with pytest.raises(PreprocessingError, match="Target column 'Class' detected"):
        preprocessor.transform(X_bad)


def test_preprocessing_unfitted_transform_rejection(sample_feature_data):
    """Verifies that transform fails if preprocessor has not been fitted."""
    _, X_val = sample_feature_data
    preprocessor = FraudPreprocessor()
    with pytest.raises(PreprocessingError, match="must be fitted"):
        preprocessor.transform(X_val)


def test_preprocessor_save_load_roundtrip(tmp_path: Path, sample_feature_data):
    """Verifies serialization and non-overwrite safeguard."""
    X_train, X_val = sample_feature_data
    preprocessor = FraudPreprocessor()
    preprocessor.fit(X_train)

    save_path = tmp_path / "test_preprocessor.joblib"
    saved = preprocessor.save(save_path)
    assert saved.exists()

    # Attempting to save again must raise FileExistsError
    with pytest.raises(FileExistsError, match="already exists"):
        preprocessor.save(save_path)

    # Loading verifies exact behavior
    loaded = FraudPreprocessor.load(save_path)
    val_scaled_original = preprocessor.transform(X_val)
    val_scaled_loaded = loaded.transform(X_val)
    pd.testing.assert_frame_equal(val_scaled_original, val_scaled_loaded)
