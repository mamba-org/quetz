"""Added create_at and expire_at date to API key

Revision ID: ebe550f9fbbe
Revises: 0653794b6252
Create Date: 2021-01-22 22:38:05.693595

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'ebe550f9fbbe'
down_revision = '0653794b6252'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=False))
        batch_op.add_column(sa.Column('expire_at', sa.DateTime(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###

    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.drop_column('expired_at')
        batch_op.drop_column('create_at')

    # ### end Alembic commands ###
