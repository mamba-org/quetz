"""Update scoped API key uploader id

Revision ID: 3ba25f23fb7d
Revises: d212023a8e0b
Create Date: 2023-08-02 08:03:09.961559

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '3ba25f23fb7d'
down_revision = 'd212023a8e0b'
branch_labels = None
depends_on = None


def upgrade():
    package_versions = sa.sql.table("package_versions", sa.sql.column("uploader_id"))
    conn = op.get_bind()
    # Get all user_id/owner_id from channel scoped API keys
    # (user is anonymous - username is null)
    res = conn.execute(
        sa.text(
            """SELECT api_keys.user_id, api_keys.owner_id FROM api_keys
            INNER JOIN users ON users.id = api_keys.user_id
            WHERE users.username is NULL;
            """
        )
    )
    results = res.fetchall()
    # Replace the uploader with the key owner (real user instead of the anonymous one)
    for result in results:
        op.execute(
            package_versions.update()
            .where(package_versions.c.uploader_id == result[0])
            .values(uploader_id=result[1])
        )


def downgrade():
    package_versions = sa.sql.table("package_versions", sa.sql.column("uploader_id"))
    conn = op.get_bind()
    # Get all user_id/owner_id from channel scoped API keys
    # (user is anonymous - username is null)
    res = conn.execute(
        sa.text(
            """SELECT api_keys.user_id, api_keys.owner_id FROM api_keys
            INNER JOIN users ON users.id = api_keys.user_id
            WHERE users.username is NULL;
            """
        )
    )
    results = res.fetchall()
    # Replace the uploader with the key anonymous user
    for result in results:
        op.execute(
            package_versions.update()
            .where(package_versions.c.uploader_id == result[1])
            .values(uploader_id=result[0])
        )
