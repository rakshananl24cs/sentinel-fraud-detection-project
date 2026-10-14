"""Monitoring service coordinating transaction window selection, drift detection, and atomic persistence."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.drift import DriftReport
from backend.app.models.transaction import Transaction
from ml.src.monitoring.drift_detector import EXPECTED_FEATURE_NAMES, get_reference_profile

logger = logging.getLogger(__name__)

MAX_SYNCHRONOUS_TRANSACTIONS: int = 10000
QUERY_CHUNK_SIZE: int = 1000


def generate_drift_report(
    db: Session,
    time_window_start: datetime,
    time_window_end: datetime,
    model_version: str = "xgb-cost-v1",
) -> DriftReport:
    """Calculates and persists a reproducible data drift report for an observation window.

    Args:
        db: Active SQLAlchemy database session.
        time_window_start: Observation window lower bound (UTC).
        time_window_end: Observation window upper bound (UTC).
        model_version: Target model version identifier.

    Returns:
        Persisted DriftReport ORM entity.

    Raises:
        HTTPException 409: If transaction count exceeds synchronous processing limit.
        HTTPException 500: If calculation or database commit fails.
    """
    # 1. Count transactions in designated window
    count_query = select(func.count(Transaction.id)).where(
        Transaction.created_at >= time_window_start,
        Transaction.created_at <= time_window_end,
    )
    total_tx_in_window = db.execute(count_query).scalar_one()

    # 2. Enforce synchronous processing bounds
    if total_tx_in_window > MAX_SYNCHRONOUS_TRANSACTIONS:
        logger.warning(
            f"Observation window transaction count ({total_tx_in_window}) exceeds limit ({MAX_SYNCHRONOUS_TRANSACTIONS})"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Observation window contains {total_tx_in_window} transactions, exceeding the synchronous "
                f"processing limit of {MAX_SYNCHRONOUS_TRANSACTIONS}. An asynchronous background-job "
                f"workflow is required for datasets of this scale."
            ),
        )

    # 3. Retrieve transactions in chunked batches without loading entire database history
    valid_feature_rows: List[Dict[str, float]] = []
    invalid_rows_count: int = 0
    quality_issues: List[Dict[str, Any]] = []

    if total_tx_in_window > 0:
        query = (
            select(Transaction.id, Transaction.payload_json)
            .where(
                Transaction.created_at >= time_window_start,
                Transaction.created_at <= time_window_end,
            )
            .order_by(Transaction.created_at.asc(), Transaction.id.asc())
        )

        # Process in chunks to prevent unbounded memory spike
        offset = 0
        while offset < total_tx_in_window:
            chunk = db.execute(query.limit(QUERY_CHUNK_SIZE).offset(offset)).all()
            if not chunk:
                break

            for tx_id, payload in chunk:
                if not isinstance(payload, dict):
                    invalid_rows_count += 1
                    quality_issues.append({"transaction_id": str(tx_id), "issue": "Malformed payload structure"})
                    continue

                # Check all 30 expected canonical features
                is_valid = True
                row_dict: Dict[str, float] = {}
                for feat in EXPECTED_FEATURE_NAMES:
                    val = payload.get(feat)
                    if val is None:
                        is_valid = False
                        quality_issues.append({"transaction_id": str(tx_id), "issue": f"Missing feature '{feat}'"})
                        break
                    try:
                        val_float = float(val)
                        if not np.isfinite(val_float):
                            is_valid = False
                            quality_issues.append({"transaction_id": str(tx_id), "issue": f"Non-finite value in '{feat}'"})
                            break
                        row_dict[feat] = val_float
                    except (ValueError, TypeError):
                        is_valid = False
                        quality_issues.append({"transaction_id": str(tx_id), "issue": f"Non-numeric value in '{feat}'"})
                        break

                if is_valid:
                    valid_feature_rows.append(row_dict)
                else:
                    invalid_rows_count += 1

            offset += len(chunk)

    # 4. Construct observed DataFrame from validated rows
    observed_df = pd.DataFrame(valid_feature_rows) if valid_feature_rows else pd.DataFrame(columns=EXPECTED_FEATURE_NAMES)

    # 5. Execute drift detection against reference training population
    ref_profile = get_reference_profile()
    try:
        report_summary = ref_profile.evaluate_dataset(
            observed_df=observed_df,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            model_version=model_version,
            invalid_rows_count=invalid_rows_count,
            quality_issues=quality_issues[:50],  # Bound quality issues list in summary
        )
    except Exception as exc:
        logger.error(f"Failed to calculate statistical drift metrics: {type(exc).__name__}: {str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute statistical distribution drift metrics.",
        )

    # 6. Atomic persistence of completed report
    now_utc = datetime.now(timezone.utc)
    try:
        drift_entity = DriftReport(
            model_version=model_version,
            metric_name=report_summary["primary_metric"]["name"],
            metric_value=float(report_summary["primary_metric"]["value"]),
            status=report_summary["overall_status"],
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            summary_json=report_summary,
            created_at=now_utc,
        )
        db.add(drift_entity)
        db.commit()
        db.refresh(drift_entity)
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to persist drift report: {type(exc).__name__}: {str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist data drift report to database.",
        )

    return drift_entity
