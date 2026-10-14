"""002_feedback_and_drift_constraints

Revision ID: dc187c3ba103
Revises: db1aec0b0a89
Create Date: 2026-10-12 12:30:43.197596

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc187c3ba103'
down_revision: Union[str, Sequence[str], None] = 'db1aec0b0a89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add retraining eligibility and drift time window constraints."""
    op.create_check_constraint(
        constraint_name="ck_feedback_retraining_eligibility",
        table_name="operator_feedback",
        condition="(is_eligible_for_retraining = FALSE) OR (is_verified = TRUE AND decision IN ('CONFIRMED_FRAUD', 'CONFIRMED_GENUINE'))",
    )
    op.create_check_constraint(
        constraint_name="ck_drift_reports_time_window",
        table_name="drift_reports",
        condition="time_window_end >= time_window_start",
    )


def downgrade() -> None:
    """Downgrade schema: drop retraining eligibility and drift time window constraints."""
    op.drop_constraint(
        constraint_name="ck_drift_reports_time_window",
        table_name="drift_reports",
        type_="check",
    )
    op.drop_constraint(
        constraint_name="ck_feedback_retraining_eligibility",
        table_name="operator_feedback",
        type_="check",
    )
