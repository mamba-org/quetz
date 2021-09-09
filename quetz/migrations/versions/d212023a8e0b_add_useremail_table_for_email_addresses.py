"""add Email table for email addresses

Revision ID: d212023a8e0b
Revises: cddba8e6e639
Create Date: 2021-09-07 18:14:30.387156

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd212023a8e0b'
down_revision = 'cddba8e6e639'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'emails',
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('identity_id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('user_id', sa.LargeBinary(length=16), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=True),
        sa.Column('primary', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ['provider', 'identity_id'],
            ['identities.provider', 'identities.identity_id'],
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
        ),
        sa.PrimaryKeyConstraint('provider', 'identity_id', 'email'),
        sa.UniqueConstraint('email'),
    )
    with op.batch_alter_table('emails', schema=None) as batch_op:
        batch_op.create_index(
            'email_index', ['provider', 'identity_id', 'email'], unique=True
        )


def downgrade():
    with op.batch_alter_table('emails', schema=None) as batch_op:
        batch_op.drop_index('email_index')

    op.drop_table('emails')
