"""003_prediction_ledger_immutability

Revision ID: 20b46b28f9db
Revises: dc187c3ba103
Create Date: 2026-10-12 12:39:02.073135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20b46b28f9db'
down_revision: Union[str, Sequence[str], None] = 'dc187c3ba103'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: enforce strict ledger immutability on predictions table."""
    # 1. Update foreign key from CASCADE to RESTRICT
    op.drop_constraint('predictions_transaction_id_fkey', 'predictions', type_='foreignkey')
    op.create_foreign_key(
        'predictions_transaction_id_fkey',
        'predictions',
        'transactions',
        ['transaction_id'],
        ['id'],
        ondelete='RESTRICT',
    )

    # 2. Create PL/pgSQL function rejecting UPDATE and DELETE on predictions
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_prediction_update_or_delete()
    RETURNS TRIGGER AS $$
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            RAISE EXCEPTION 'Prediction records are immutable: UPDATE operations on predictions are prohibited (record ID: %)', OLD.id;
        ELSIF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Prediction records are immutable: DELETE operations on predictions are prohibited (record ID: %)', OLD.id;
        END IF;
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # 3. Attach trigger to predictions table for UPDATE and DELETE
    op.execute("""
    CREATE TRIGGER trg_predictions_immutable
    BEFORE UPDATE OR DELETE ON predictions
    FOR EACH ROW
    EXECUTE FUNCTION prevent_prediction_update_or_delete();
    """)


def downgrade() -> None:
    """Downgrade schema: remove trigger and restore CASCADE foreign key."""
    # 1. Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trg_predictions_immutable ON predictions;")
    op.execute("DROP FUNCTION IF EXISTS prevent_prediction_update_or_delete();")

    # 2. Revert foreign key to CASCADE
    op.drop_constraint('predictions_transaction_id_fkey', 'predictions', type_='foreignkey')
    op.create_foreign_key(
        'predictions_transaction_id_fkey',
        'predictions',
        'transactions',
        ['transaction_id'],
        ['id'],
        ondelete='CASCADE',
    )
