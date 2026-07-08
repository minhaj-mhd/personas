"""Add panels and panel_messages

Persists multi-agent voice panels: a named roster of personas (persona_ids JSON)
and their transcript (panel_messages), so a panel can be resumed with full chat
history across sessions.

Revision ID: a1f2c3d4e5f6
Revises: eff19a00e7fa
Create Date: 2026-07-08 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "eff19a00e7fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "panels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("persona_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "panel_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("panel_id", sa.UUID(), nullable=False),
        sa.Column("speaker", sa.String(), nullable=False),
        sa.Column("persona_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["panel_id"], ["panels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_panel_messages_panel_id", "panel_messages", ["panel_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_panel_messages_panel_id", table_name="panel_messages")
    op.drop_table("panel_messages")
    op.drop_table("panels")
