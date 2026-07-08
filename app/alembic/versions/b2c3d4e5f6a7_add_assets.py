"""Add assets

Stores binary uploads (images) attached to a persona or a panel for visual
injection into live sessions. Bytes are kept in Postgres (BYTEA).

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-07-08 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1f2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("persona_id", sa.UUID(), nullable=True),
        sa.Column("panel_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["persona_id"], ["personas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["panel_id"], ["panels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_persona_id", "assets", ["persona_id"], unique=False)
    op.create_index("ix_assets_panel_id", "assets", ["panel_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_assets_panel_id", table_name="assets")
    op.drop_index("ix_assets_persona_id", table_name="assets")
    op.drop_table("assets")
