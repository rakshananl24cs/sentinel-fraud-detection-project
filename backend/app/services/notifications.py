"""Fraud Alert and Notification dispatching service.

Generates structured high-risk (BLOCK) and review-needed (REVIEW) alerts
from actual model predictions, persisting them to PostgreSQL while providing
optional external delivery (Email/SMS) hooks with strict truth-in-reporting.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.alert import FraudAlert
from backend.app.models.prediction import Prediction
from backend.app.models.transaction import Transaction

logger = logging.getLogger(__name__)

DISCLAIMER_TEXT = "Model predictions indicate statistical risk and do not independently confirm fraud."


def generate_alert_content(
    external_id: str,
    decision: str,
    fraud_probability: float,
    amount: float,
) -> Tuple[str, str, str, str, str]:
    """Builds standard, policy-compliant alert message content from actual prediction data.

    Returns:
        (alert_type, severity, title, message, recommended_action)
    """
    prob_pct = f"{round(fraud_probability * 100)}%"
    amount_str = f"${amount:,.2f}"

    if decision == "BLOCK":
        alert_type = "HIGH_RISK"
        severity = "HIGH"
        title = f"High-Risk Transaction Detected: {external_id}"
        message = (
            f"High-Risk Transaction Detected: Transaction {external_id} has an estimated "
            f"fraud probability of {prob_pct} and has been blocked under the current policy. "
            f"Please investigate the transaction."
        )
        recommended_action = (
            "Immediate block enforced. Restrict account permissions, investigate transaction details, "
            "contact cardholder to confirm authenticity, and inspect velocity patterns."
        )
    elif decision == "REVIEW":
        alert_type = "NEEDS_REVIEW"
        severity = "MEDIUM"
        title = f"Transaction Needs Review: {external_id}"
        message = (
            f"Transaction Needs Review: Transaction {external_id} has an estimated "
            f"fraud probability of {prob_pct} and requires human review under the current policy. "
            f"Please inspect and adjudicate the case in the review queue."
        )
        recommended_action = (
            "Open case in Fraud Review Queue. Inspect local SHAP risk drivers and verify "
            "cardholder location before releasing or declining payment."
        )
    else:
        raise ValueError(
            f"Fraud alerts must only be generated for 'BLOCK' or 'REVIEW' decisions, not '{decision}'."
        )

    return alert_type, severity, title, message, recommended_action


def create_fraud_alert(
    db: Session,
    transaction: Transaction,
    prediction: Prediction,
    amount: float,
    external_id: str,
) -> Optional[FraudAlert]:
    """Persists a new FraudAlert record if the prediction decision is BLOCK or REVIEW.

    Guarantees:
    - Never generates alerts for APPROVE.
    - Idempotent: does not duplicate alerts for the same transaction and alert type.
    - Stored atomically within the provided database session.
    """
    decision = prediction.decision
    if decision not in ("BLOCK", "REVIEW"):
        return None

    alert_type, severity, title, message, recommended_action = generate_alert_content(
        external_id=external_id,
        decision=decision,
        fraud_probability=prediction.calibrated_probability,
        amount=amount,
    )

    # Check for existing alert for this transaction to avoid duplicates
    existing_alert = db.execute(
        select(FraudAlert).where(
            FraudAlert.transaction_id == transaction.id,
            FraudAlert.alert_type == alert_type,
        )
    ).scalar_one_or_none()

    if existing_alert is not None:
        return existing_alert

    now_utc = datetime.now(timezone.utc)
    alert = FraudAlert(
        id=uuid.uuid4(),
        transaction_id=transaction.id,
        external_id=external_id,
        prediction_id=prediction.id,
        alert_type=alert_type,
        severity=severity,
        decision=decision,
        fraud_probability=prediction.calibrated_probability,
        amount=Decimal(str(round(amount, 2))),
        title=title,
        message=message,
        recommended_action=recommended_action,
        disclaimer=DISCLAIMER_TEXT,
        is_read=False,
        read_at=None,
        created_at=now_utc,
    )
    db.add(alert)
    db.flush()

    # Dispatch external notification if configured
    dispatch_external_notifications(alert)

    return alert


def dispatch_external_notifications(alert: FraudAlert) -> Dict[str, Any]:
    """Evaluates external delivery channels (Email/SMS).

    STRICT TRUTH-IN-REPORTING:
    Never claims an email or SMS was sent unless external provider credentials
    are configured and delivery is successfully confirmed.
    """
    results: Dict[str, Any] = {
        "in_app": "DELIVERED",
        "email": "NOT_CONFIGURED",
        "sms": "NOT_CONFIGURED",
    }

    enable_email = os.getenv("ENABLE_EMAIL_ALERTS", "false").lower() in ("true", "1")
    enable_sms = os.getenv("ENABLE_SMS_ALERTS", "false").lower() in ("true", "1")

    if not enable_email:
        logger.debug(
            "External email delivery skipped for alert %s: ENABLE_EMAIL_ALERTS is false or unconfigured.",
            alert.id,
        )
    else:
        # Configuration check
        smtp_host = os.getenv("SMTP_HOST")
        if not smtp_host:
            logger.warning(
                "Email delivery enabled but SMTP_HOST is not configured. Alert %s not emailed.",
                alert.id,
            )
            results["email"] = "MISSING_CONFIGURATION"
        else:
            # Here real SMTP delivery would execute. For local dev without mock claims:
            logger.info("Email alert delivery configured for host: %s", smtp_host)
            results["email"] = "PENDING_DELIVERY"

    if not enable_sms:
        logger.debug(
            "External SMS delivery skipped for alert %s: ENABLE_SMS_ALERTS is false or unconfigured.",
            alert.id,
        )
    else:
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        if not twilio_sid:
            logger.warning(
                "SMS delivery enabled but TWILIO_ACCOUNT_SID is not configured. Alert %s not sent.",
                alert.id,
            )
            results["sms"] = "MISSING_CONFIGURATION"
        else:
            logger.info("SMS alert delivery configured for Twilio SID: %s", twilio_sid[:8] + "...")
            results["sms"] = "PENDING_DELIVERY"

    return results
