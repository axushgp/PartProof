"""feat_add_approval_unique_plan_hash_constraint

Revision ID: 91eed4defee2
Revises: f6ca88a5db34
Create Date: 2026-11-06 10:17:56.317940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91eed4defee2'
down_revision: Union[str, Sequence[str], None] = 'f6ca88a5db34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('approvals') as batch_op:
        batch_op.create_unique_constraint('uq_approvals_task_plan_hash', ['task_id', 'approved_plan_hash'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('approvals') as batch_op:
        batch_op.drop_constraint('uq_approvals_task_plan_hash', type_='unique')
