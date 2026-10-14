"""Transaction ingestion and synchronous fraud scoring endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.deps import require_role
from backend.app.db.session import get_db
from backend.app.models.audit import AuditLog
from backend.app.models.prediction import Prediction
from backend.app.models.transaction import Transaction
from backend.app.models.user import User
from backend.app.schemas.transaction import (
    BatchItemResult,
    BatchPredictRequest,
    BatchPredictResponse,
    BatchSummary,
    OperationalStatsResponse,
    RecentTransactionItem,
    RecentTransactionsResponse,
    TransactionPredictRequest,
    TransactionPredictResponse,
)
from ml.src.models.inference import InferenceError, predict_fraud
from backend.app.services.notifications import create_fraud_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["Transactions & Scoring"])


@router.post(
    "/predict",
    response_model=TransactionPredictResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"model": TransactionPredictResponse, "description": "Transaction scored and persisted"},
        status.HTTP_409_CONFLICT: {"description": "Duplicate transaction identifier"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Invalid feature schema or non-finite values"},
    },
    summary="Synchronous Fraud Scoring",
    description=(
        "Ingests a financial transaction with 30 canonical features, executes calibrated "
        "XGBoost risk inference, evaluates the cost-sensitive three-way decision policy "
        "(APPROVE, REVIEW, BLOCK), generates local SHAP feature attributions, and atomically "
        "persists the transaction and immutable prediction records."
    ),
)
def score_and_ingest_transaction(
    payload: TransactionPredictRequest,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> TransactionPredictResponse:
    """Synchronously scores an ingested transaction and stores immutable prediction audit records."""
    # 1. Resolve unique external transaction ID
    external_id = payload.external_id or f"TX-{int(datetime.now(timezone.utc).timestamp() * 1000)}-{uuid.uuid4().hex[:6]}"

    # 2. Check for duplicate transaction identifier
    existing_tx = db.execute(
        select(Transaction).where(Transaction.external_id == external_id)
    ).scalar_one_or_none()
    if existing_tx is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transaction with identifier '{external_id}' already exists.",
        )

    # 3. Extract exact 30 canonical features and execute ML inference
    features_dict = payload.get_features_dict()
    try:
        scoring_input = {**features_dict, "transaction_id": external_id}
        ml_result = predict_fraud(scoring_input)
    except InferenceError as exc:
        logger.error("Inference validation error: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Inference validation error: {str(exc)}",
        )
    except Exception as exc:
        logger.error("Unexpected error in ML inference pipeline: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Machine learning inference service encountered an internal error.",
        )

    # 4. Atomic database persistence
    now_utc = datetime.now(timezone.utc)
    try:
        tx = Transaction(
            external_id=external_id,
            amount=Decimal(str(round(payload.Amount, 2))),
            payload_json=features_dict,
            created_at=now_utc,
        )
        db.add(tx)
        db.flush()  # Generates tx.id for child prediction foreign key

        pred = Prediction(
            transaction_id=tx.id,
            model_version=ml_result["model_version"],
            raw_probability=ml_result["raw_probability"],
            calibrated_probability=ml_result["fraud_probability"],
            risk_level=ml_result["risk_level"],
            decision=ml_result["decision"],
            expected_cost=ml_result["expected_cost"],
            policy_parameters_json=ml_result["policy_parameters"],
            explanation_json=ml_result["explanation"],
            created_at=now_utc,
        )
        db.add(pred)
        db.flush()

        # Generate persistent alert notification for BLOCK or REVIEW
        if ml_result["decision"] in ("BLOCK", "REVIEW"):
            create_fraud_alert(
                db=db,
                transaction=tx,
                prediction=pred,
                amount=float(payload.Amount),
                external_id=external_id,
            )

        db.commit()
        db.refresh(pred)
    except IntegrityError as exc:
        db.rollback()
        err_msg = str(exc).lower()
        if "ix_transactions_external_id" in err_msg or "unique" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transaction with identifier '{external_id}' already exists.",
            )
        logger.error("Integrity error during transaction and prediction storage: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database integrity failure while storing scoring records.",
        )
    except Exception as exc:
        db.rollback()
        logger.error("Unexpected error persisting scoring records: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while persisting transaction records.",
        )

    # 5. Build and return documented API response
    return TransactionPredictResponse(
        prediction_id=pred.id,
        transaction_id=external_id,
        external_id=external_id,
        model_version=pred.model_version,
        decision=pred.decision,
        risk_level=pred.risk_level,
        fraud_probability=pred.calibrated_probability,
        raw_probability=pred.raw_probability,
        expected_cost=pred.expected_cost,
        policy_parameters=pred.policy_parameters_json,
        explanation=pred.explanation_json,
        created_at=pred.created_at,
    )


@router.post(
    "/batch-predict",
    response_model=BatchPredictResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Batch CSV Fraud Analysis",
    description=(
        "Scores an array of transactions in batch using the calibrated XGBoost model "
        "and cost-sensitive decision policy. Persists transaction records, prediction "
        "records, and an immutable audit log entry for the batch execution."
    ),
)
def batch_score_transactions(
    payload: BatchPredictRequest,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> BatchPredictResponse:
    """Performs batch fraud inference and persists transaction and prediction records."""
    now_utc = datetime.now(timezone.utc)
    batch_id = payload.batch_id or f"BATCH-{int(now_utc.timestamp())}-{uuid.uuid4().hex[:6]}"
    filename = payload.filename or "uploaded_transactions.csv"

    # Pre-fetch existing external IDs in DB to prevent unique constraint conflicts
    provided_ids = [item.external_id for item in payload.items if item.external_id]
    existing_external_ids = set()
    if provided_ids:
        for chunk_start in range(0, len(provided_ids), 500):
            chunk = provided_ids[chunk_start : chunk_start + 500]
            found = db.execute(
                select(Transaction.external_id).where(Transaction.external_id.in_(chunk))
            ).scalars().all()
            existing_external_ids.update(found)

    scored_items: List[BatchItemResult] = []
    seen_in_batch = set()

    approved_count = 0
    review_count = 0
    block_count = 0
    low_risk_count = 0
    medium_risk_count = 0
    high_risk_count = 0
    total_amount = 0.0
    sum_fraud_probability = 0.0
    failed_count = 0

    try:
        for idx, item in enumerate(payload.items):
            # 1. Resolve unique external_id
            if item.external_id:
                candidate_id = item.external_id
                if candidate_id in existing_external_ids or candidate_id in seen_in_batch:
                    resolved_id = f"{candidate_id}-B{uuid.uuid4().hex[:4]}"
                else:
                    resolved_id = candidate_id
            else:
                resolved_id = f"TX-{batch_id}-{idx + 1:04d}"

            seen_in_batch.add(resolved_id)

            # 2. Extract features and execute inference per item
            try:
                features_dict = item.get_features_dict()
                scoring_input = {**features_dict, "transaction_id": resolved_id}
                ml_result = predict_fraud(scoring_input)

                amount_val = round(item.Amount, 2)
                decision = ml_result["decision"]
                risk_level = ml_result["risk_level"]
                fraud_prob = ml_result["fraud_probability"]
                raw_prob = ml_result["raw_probability"]
                expected_cost = ml_result["expected_cost"]
                model_version = ml_result["model_version"]

                with db.begin_nested():
                    tx = Transaction(
                        external_id=resolved_id,
                        amount=Decimal(str(amount_val)),
                        payload_json={
                            "batch_id": batch_id,
                            "filename": filename,
                            **features_dict,
                        },
                        created_at=now_utc,
                    )
                    db.add(tx)
                    db.flush()

                    pred = Prediction(
                        transaction_id=tx.id,
                        model_version=model_version,
                        raw_probability=raw_prob,
                        calibrated_probability=fraud_prob,
                        risk_level=risk_level,
                        decision=decision,
                        expected_cost=expected_cost,
                        policy_parameters_json=ml_result["policy_parameters"],
                        explanation_json=ml_result["explanation"],
                        created_at=now_utc,
                    )
                    db.add(pred)
                    db.flush()

                    # Generate persistent alert notification for BLOCK or REVIEW
                    if decision in ("BLOCK", "REVIEW"):
                        create_fraud_alert(
                            db=db,
                            transaction=tx,
                            prediction=pred,
                            amount=amount_val,
                            external_id=resolved_id,
                        )

                # Tally counts only on successful score & persistence
                if decision == "APPROVE":
                    approved_count += 1
                elif decision == "REVIEW":
                    review_count += 1
                elif decision == "BLOCK":
                    block_count += 1

                if risk_level == "LOW":
                    low_risk_count += 1
                elif risk_level == "MEDIUM":
                    medium_risk_count += 1
                elif risk_level == "HIGH":
                    high_risk_count += 1

                total_amount += amount_val
                sum_fraud_probability += fraud_prob

                scored_items.append(
                    BatchItemResult(
                        transaction_id=resolved_id,
                        external_id=resolved_id,
                        amount=amount_val,
                        decision=decision,
                        risk_level=risk_level,
                        fraud_probability=fraud_prob,
                        raw_probability=raw_prob,
                        expected_cost=expected_cost,
                        model_version=model_version,
                        created_at=now_utc,
                        status="SUCCESS",
                        error=None,
                    )
                )
            except Exception as item_exc:
                logger.warning("Error processing batch item %d (%s): %s", idx + 1, resolved_id, str(item_exc))
                failed_count += 1
                amount_val = round(item.Amount, 2) if hasattr(item, "Amount") and item.Amount is not None else None
                scored_items.append(
                    BatchItemResult(
                        transaction_id=resolved_id,
                        external_id=resolved_id,
                        amount=amount_val,
                        decision="FAILED",
                        risk_level="UNKNOWN",
                        fraud_probability=None,
                        raw_probability=None,
                        expected_cost=None,
                        model_version=None,
                        created_at=now_utc,
                        status="ERROR",
                        error=f"Row {idx + 1}: {str(item_exc)}",
                    )
                )

        total_proc = len([item for item in scored_items if item.status == "SUCCESS"])
        avg_fraud_prob = round(sum_fraud_probability / total_proc, 5) if total_proc > 0 else 0.0

        summary = BatchSummary(
            batch_id=batch_id,
            filename=filename,
            total_submitted=len(payload.items),
            total_processed=total_proc,
            failed_count=failed_count,
            approved_count=approved_count,
            review_count=review_count,
            block_count=block_count,
            low_risk_count=low_risk_count,
            medium_risk_count=medium_risk_count,
            high_risk_count=high_risk_count,
            total_amount=round(total_amount, 2),
            average_fraud_probability=avg_fraud_prob,
            created_at=now_utc,
        )

        # Audit log persistence
        audit_metadata = summary.model_dump(mode="json")
        audit_metadata["items"] = [item.model_dump(mode="json") for item in scored_items]

        audit_entry = AuditLog(
            user_id=current_user.id if current_user else None,
            action="BATCH_CSV_ANALYSIS",
            entity_type="SYSTEM",
            entity_id=batch_id,
            metadata_json=audit_metadata,
            created_at=now_utc,
        )
        db.add(audit_entry)
        db.commit()

        return BatchPredictResponse(summary=summary, items=scored_items)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("Error processing batch scoring: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the batch fraud scoring request.",
        )


@router.get(
    "/batches/latest",
    response_model=BatchPredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Analyzed Batch",
    description="Returns the most recently analyzed transaction batch, including KPIs, distributions, and scored records.",
)
def get_latest_batch(
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> BatchPredictResponse:
    """Retrieves the latest analyzed transaction batch."""
    audits = db.execute(
        select(AuditLog)
        .where(AuditLog.action == "BATCH_CSV_ANALYSIS")
        .order_by(desc(AuditLog.created_at))
        .limit(10)
    ).scalars().all()

    if not audits:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No transaction batch has been analyzed yet.",
        )

    # Prefer latest batch with successfully scored transactions (total_processed > 0)
    selected_audit = next(
        (a for a in audits if isinstance(a.metadata_json, dict) and a.metadata_json.get("total_processed", 0) > 0),
        audits[0]
    )

    meta = selected_audit.metadata_json or {}
    summary = BatchSummary(
        batch_id=meta.get("batch_id", selected_audit.entity_id or "UNKNOWN"),
        filename=meta.get("filename", "uploaded_batch.csv"),
        total_submitted=meta.get("total_submitted", 0),
        total_processed=meta.get("total_processed", 0),
        failed_count=meta.get("failed_count", 0),
        approved_count=meta.get("approved_count", 0),
        review_count=meta.get("review_count", 0),
        block_count=meta.get("block_count", 0),
        low_risk_count=meta.get("low_risk_count", 0),
        medium_risk_count=meta.get("medium_risk_count", 0),
        high_risk_count=meta.get("high_risk_count", 0),
        total_amount=float(meta.get("total_amount", 0.0)),
        average_fraud_probability=float(meta.get("average_fraud_probability", 0.0)),
        created_at=selected_audit.created_at,
    )

    items_data = meta.get("items", [])
    items = [BatchItemResult(**item) for item in items_data]

    return BatchPredictResponse(summary=summary, items=items)


@router.get(
    "/batches/{batch_id}",
    response_model=BatchPredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Analyzed Batch By ID",
    description="Returns results and metrics for a specific batch identifier.",
)
def get_batch_by_id(
    batch_id: str,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> BatchPredictResponse:
    """Retrieves a specific analyzed batch by its identifier."""
    audit = db.execute(
        select(AuditLog)
        .where(AuditLog.action == "BATCH_CSV_ANALYSIS", AuditLog.entity_id == batch_id)
        .order_by(desc(AuditLog.created_at))
        .limit(1)
    ).scalar_one_or_none()

    if audit is None or not isinstance(audit.metadata_json, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch '{batch_id}' was not found.",
        )

    meta = audit.metadata_json
    summary = BatchSummary(
        batch_id=meta.get("batch_id", audit.entity_id or batch_id),
        filename=meta.get("filename", "uploaded_batch.csv"),
        total_submitted=meta.get("total_submitted", 0),
        total_processed=meta.get("total_processed", 0),
        failed_count=meta.get("failed_count", 0),
        approved_count=meta.get("approved_count", 0),
        review_count=meta.get("review_count", 0),
        block_count=meta.get("block_count", 0),
        low_risk_count=meta.get("low_risk_count", 0),
        medium_risk_count=meta.get("medium_risk_count", 0),
        high_risk_count=meta.get("high_risk_count", 0),
        total_amount=float(meta.get("total_amount", 0.0)),
        average_fraud_probability=float(meta.get("average_fraud_probability", 0.0)),
        created_at=audit.created_at,
    )

    items_data = meta.get("items", [])
    items = [BatchItemResult(**item) for item in items_data]

    return BatchPredictResponse(summary=summary, items=items)


@router.get(
    "/operational-stats",
    response_model=OperationalStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Cumulative Operational Statistics",
    description="Aggregates decision counts, risk distribution, and monetary volume across all historical transaction records.",
)
def get_operational_stats(
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> OperationalStatsResponse:
    """Computes global operational metrics across all persisted transaction records."""
    total_tx = db.execute(select(func.count(Prediction.id))).scalar_one() or 0
    approved = db.execute(select(func.count(Prediction.id)).where(Prediction.decision == "APPROVE")).scalar_one() or 0
    review = db.execute(select(func.count(Prediction.id)).where(Prediction.decision == "REVIEW")).scalar_one() or 0
    block = db.execute(select(func.count(Prediction.id)).where(Prediction.decision == "BLOCK")).scalar_one() or 0
    low_risk = db.execute(select(func.count(Prediction.id)).where(Prediction.risk_level == "LOW")).scalar_one() or 0
    med_risk = db.execute(select(func.count(Prediction.id)).where(Prediction.risk_level == "MEDIUM")).scalar_one() or 0
    high_risk = db.execute(select(func.count(Prediction.id)).where(Prediction.risk_level == "HIGH")).scalar_one() or 0
    total_amt = db.execute(select(func.coalesce(func.sum(Transaction.amount), 0))).scalar_one() or 0.0
    avg_prob = db.execute(select(func.coalesce(func.avg(Prediction.calibrated_probability), 0.0))).scalar_one() or 0.0
    latest_at = db.execute(select(func.max(Prediction.created_at))).scalar_one()

    return OperationalStatsResponse(
        total_transactions=int(total_tx),
        approved_count=int(approved),
        review_count=int(review),
        block_count=int(block),
        low_risk_count=int(low_risk),
        medium_risk_count=int(med_risk),
        high_risk_count=int(high_risk),
        total_amount=float(total_amt),
        average_fraud_probability=round(float(avg_prob), 5),
        latest_transaction_at=latest_at,
    )


@router.get(
    "/recent",
    response_model=RecentTransactionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Recent Transactions",
    description="Returns the most recently scored transactions across all activity or filtered by batch/decision.",
)
def get_recent_transactions(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    decision: Optional[str] = Query(default=None, regex="^(APPROVE|REVIEW|BLOCK)$"),
    batch_id: Optional[str] = Query(default=None),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> RecentTransactionsResponse:
    """Returns recently processed transactions joined with their latest predictions."""
    pred_subq = (
        select(
            Prediction.transaction_id.label("tx_id"),
            Prediction.decision.label("decision"),
            Prediction.risk_level.label("risk_level"),
            Prediction.calibrated_probability.label("calibrated_probability"),
            Prediction.created_at.label("pred_created_at"),
            func.row_number()
            .over(
                partition_by=Prediction.transaction_id,
                order_by=(desc(Prediction.created_at), desc(Prediction.id)),
            )
            .label("rn"),
        )
        .subquery()
    )

    base_query = (
        select(
            Transaction.id,
            Transaction.external_id,
            Transaction.amount,
            Transaction.payload_json,
            pred_subq.c.decision,
            pred_subq.c.risk_level,
            pred_subq.c.calibrated_probability,
            Transaction.created_at,
        )
        .join(pred_subq, pred_subq.c.tx_id == Transaction.id)
        .where(pred_subq.c.rn == 1)
    )

    if decision:
        base_query = base_query.where(pred_subq.c.decision == decision)

    if batch_id:
        base_query = base_query.where(Transaction.payload_json["batch_id"].as_string() == batch_id)

    total = db.execute(select(func.count()).select_from(base_query.order_by(None).subquery())).scalar_one() or 0

    rows = db.execute(
        base_query.order_by(desc(Transaction.created_at), desc(Transaction.id))
        .limit(limit)
        .offset(offset)
    ).all()

    items = []
    for row in rows:
        tx_batch_id = None
        if isinstance(row.payload_json, dict):
            tx_batch_id = row.payload_json.get("batch_id")

        items.append(
            RecentTransactionItem(
                id=row.id,
                external_id=row.external_id,
                amount=float(row.amount),
                decision=row.decision or "UNKNOWN",
                risk_level=row.risk_level or "UNKNOWN",
                fraud_probability=float(row.calibrated_probability or 0.0),
                created_at=row.created_at,
                batch_id=tx_batch_id,
            )
        )

    return RecentTransactionsResponse(items=items, total=total, limit=limit, offset=offset)

