"""Add source_type and source_url to books table

Support MOBI and GitBook imports by tracking the original source format.

Revision ID: 025_add_book_source_fields
Revises: 024_read_progress_chapters
Create Date: 2026-05-07

"""
from alembic import op
import sqlalchemy as sa


revision = "025_add_book_source_fields"
down_revision = "024_read_progress_chapters"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "books",
        sa.Column("source_type", sa.String(), server_default="epub"),
    )
    op.add_column(
        "books",
        sa.Column("source_url", sa.String(), nullable=True),
    )


def downgrade():
    op.drop_column("books", "source_url")
    op.drop_column("books", "source_type")
