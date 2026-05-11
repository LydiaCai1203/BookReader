"""Add toc_json to books table

Revision ID: 026_add_book_toc_json
Revises: 025_add_book_source_fields
Create Date: 2026-05-11

"""
from alembic import op
import sqlalchemy as sa


revision = "026_add_book_toc_json"
down_revision = "025_add_book_source_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("books", sa.Column("toc_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("books", "toc_json")
