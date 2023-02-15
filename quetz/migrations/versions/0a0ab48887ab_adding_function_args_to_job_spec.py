"""adding function args to job spec

Revision ID: 0a0ab48887ab
Revises: 3c3288034362
Create Date: 2021-02-24 16:58:56.886842

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '0a0ab48887ab'
down_revision = '3c3288034362'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('extra_args', sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('extra_args')
