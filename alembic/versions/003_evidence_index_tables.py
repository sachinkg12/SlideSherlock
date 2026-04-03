"""Evidence index tables: slides, sources, evidence_items, source_refs, claim_links, entity_links

Revision ID: 003
Revises: 002
Create Date: 2024-01-28 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slides",
        sa.Column("slide_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=False),
        sa.Column("slide_title", sa.Text(), nullable=True),
        sa.Column("png_artifact_id", sa.String(), nullable=True),
        sa.Column("pptx_ref", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"]),
        sa.ForeignKeyConstraint(["png_artifact_id"], ["artifacts.artifact_id"]),
        sa.PrimaryKeyConstraint("slide_id"),
    )

    op.create_table(
        "sources",
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=True),
        sa.Column("slide_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.artifact_id"]),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.slide_id"]),
        sa.PrimaryKeyConstraint("source_id"),
    )

    op.create_table(
        "evidence_items",
        sa.Column("evidence_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("slide_id", sa.String(), nullable=True),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"]),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.slide_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.source_id"]),
        sa.PrimaryKeyConstraint("evidence_id"),
    )

    op.create_table(
        "source_refs",
        sa.Column("ref_id", sa.String(), nullable=False),
        sa.Column("evidence_id", sa.String(), nullable=False),
        sa.Column("ref_type", sa.String(), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=True),
        sa.Column("ppt_shape_id", sa.String(), nullable=True),
        sa.Column("ppt_paragraph_ix", sa.Integer(), nullable=True),
        sa.Column("ppt_run_ix", sa.Integer(), nullable=True),
        sa.Column("bbox_x", sa.Float(), nullable=True),
        sa.Column("bbox_y", sa.Float(), nullable=True),
        sa.Column("bbox_w", sa.Float(), nullable=True),
        sa.Column("bbox_h", sa.Float(), nullable=True),
        sa.Column("page_num", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.evidence_id"]),
        sa.PrimaryKeyConstraint("ref_id"),
    )

    op.create_table(
        "claim_links",
        sa.Column("claim_link_id", sa.String(), nullable=False),
        sa.Column("claim_id", sa.String(), nullable=False),
        sa.Column("evidence_id", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.evidence_id"]),
        sa.PrimaryKeyConstraint("claim_link_id"),
    )

    op.create_table(
        "entity_links",
        sa.Column("entity_link_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("evidence_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.evidence_id"]),
        sa.PrimaryKeyConstraint("entity_link_id"),
    )


def downgrade() -> None:
    op.drop_table("entity_links")
    op.drop_table("claim_links")
    op.drop_table("source_refs")
    op.drop_table("evidence_items")
    op.drop_table("sources")
    op.drop_table("slides")
