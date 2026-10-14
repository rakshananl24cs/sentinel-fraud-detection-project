"""004_create_fraud_alerts_table

Revision ID: a4f89d71c12e
Revises: 20b46b28f9db
Create Date: 2026-10-14 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4f89d71c12e'
down_revision: Union[str, Sequence[str], None] = '20b46b28f9db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create fraud_alerts table for high-risk and review-needed notifications."""
    op.create_table(
        'fraud_alerts',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('transaction_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('external_id', sa.String(length=100), nullable=False),
        sa.Column('prediction_id', sa.Uuid(as_uuid=True), nullable=True),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('fraud_probability', sa.Float(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('recommended_action', sa.Text(), nullable=False),
        sa.Column('disclaimer', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='RESTRICT'),
        sa.CheckConstraint("alert_type IN ('HIGH_RISK', 'NEEDS_REVIEW')", name='ck_fraud_alert_type'),
        sa.CheckConstraint("decision IN ('BLOCK', 'REVIEW')", name='ck_fraud_alert_decision'),
    )
    op.create_index('ix_fraud_alerts_transaction_id', 'fraud_alerts', ['transaction_id'])
    op.create_index('ix_fraud_alerts_external_id', 'fraud_alerts', ['external_id'])
    op.create_index('ix_fraud_alerts_prediction_id', 'fraud_alerts', ['prediction_id'])
    op.create_index('ix_fraud_alerts_alert_type', 'fraud_alerts', ['alert_type'])
    op.create_index('ix_fraud_alerts_is_read', 'fraud_alerts', ['is_read'])
    op.create_index('ix_fraud_alerts_created_at', 'fraud_alerts', ['created_at'])


def downgrade() -> None:
    """Drop fraud_alerts table."""
    op.drop_index('ix_fraud_alerts_created_at', table_name='fraud_alerts')
    op.drop_index('ix_fraud_alerts_is_read', table_name='fraud_alerts')
    op.drop_index('ix_fraud_alerts_alert_type', table_name='fraud_alerts')
    op.drop_index('ix_fraud_alerts_prediction_id', table_name='fraud_alerts')
    op.drop_index('ix_fraud_alerts_external_id', table_name='fraud_alerts')
    op.drop_index('ix_fraud_alerts_transaction_id', table_name='fraud_alerts')
    op.drop_table('fraud_alerts')
