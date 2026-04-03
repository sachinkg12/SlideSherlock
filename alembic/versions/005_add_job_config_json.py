"""Add config_json to jobs (vision config, etc.)

Revision ID: 005
Revises: 004
Create Date: 2024-01-31 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("config_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "config_json")
