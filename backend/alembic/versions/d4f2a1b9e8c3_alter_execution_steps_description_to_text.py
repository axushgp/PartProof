"""alter_execution_steps_description_to_text

Revision ID: d4f2a1b9e8c3
Revises: c7b1e8432a10
Create Date: 2026-11-08 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f2a1b9e8c3'
down_revision: Union[str, Sequence[str], None] = 'c7b1e8432a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: alter execution_steps.description to Text to accommodate full descriptions."""
    with op.batch_alter_table('execution_steps') as batch_op:
        batch_op.alter_column(
            'description',
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema: alter execution_steps.description back to String(255)."""
    with op.batch_alter_table('execution_steps') as batch_op:
        batch_op.alter_column(
            'description',
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=False,
        )
