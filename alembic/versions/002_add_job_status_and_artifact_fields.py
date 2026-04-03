"""Add QUEUED and RUNNING job status, add sha256 and size_bytes to artifacts

Revision ID: 002
Revises: 001
Create Date: 2024-01-27 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update JobStatus enum to include QUEUED and RUNNING
    # PostgreSQL doesn't support IF NOT EXISTS for ALTER TYPE, so we use a DO block
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'QUEUED'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'jobstatus')
            ) THEN
                ALTER TYPE jobstatus ADD VALUE 'QUEUED';
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'RUNNING'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'jobstatus')
            ) THEN
                ALTER TYPE jobstatus ADD VALUE 'RUNNING';
            END IF;
        END $$;
        """
    )

    # Add sha256 and size_bytes columns to artifacts table
    op.add_column("artifacts", sa.Column("sha256", sa.String(), nullable=True))
    op.add_column("artifacts", sa.Column("size_bytes", sa.String(), nullable=True))


def downgrade() -> None:
    # Remove columns from artifacts table
    op.drop_column("artifacts", "size_bytes")
    op.drop_column("artifacts", "sha256")

    # Note: PostgreSQL doesn't support removing enum values easily
    # The enum values QUEUED and RUNNING will remain but won't be used
