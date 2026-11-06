"""feat_add_execution_timeout_and_step_attempt

Revision ID: c7b1e8432a10
Revises: 91eed4defee2
Create Date: 2026-11-06 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7b1e8432a10'
down_revision: Union[str, Sequence[str], None] = '91eed4defee2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('executions') as batch_op:
        batch_op.add_column(sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='30'))

    with op.batch_alter_table('execution_steps') as batch_op:
        batch_op.add_column(sa.Column('attempt_number', sa.Integer(), nullable=False, server_default='1'))
        batch_op.create_unique_constraint('uq_execution_step_attempt', ['execution_id', 'step_number', 'attempt_number'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('execution_steps') as batch_op:
        batch_op.drop_constraint('uq_execution_step_attempt', type_='unique')
        batch_op.drop_column('attempt_number')

    with op.batch_alter_table('executions') as batch_op:
        batch_op.drop_column('timeout_seconds')
