"""Persistence helpers for saved panels — used by the panel WebSocket to write the
live transcript to the DB as it happens, so a panel can be resumed with full history.

Kept separate from session.py (pure in-memory state) so the real-time endpoint can
append rows without the state layer taking a DB dependency."""

import uuid
import logging
from datetime import datetime, timezone

from app.db import async_session_maker
from app.models.panel import Panel, PanelMessage

logger = logging.getLogger(__name__)


async def load_panel(panel_id: uuid.UUID) -> Panel | None:
    """Return the Panel row, or None if this id is an ephemeral/unsaved session."""
    async with async_session_maker() as db:
        return await db.get(Panel, panel_id)


async def append_panel_message(
    panel_id: uuid.UUID,
    speaker: str,
    content: str,
    persona_id: uuid.UUID | None = None,
) -> None:
    """Append one transcript line to a saved panel and bump its updated_at.

    No-ops silently on empty content or a missing panel so the live loop never
    crashes on a persistence hiccup (best-effort, mirrors chat message persistence)."""
    if not content or not content.strip():
        return
    try:
        async with async_session_maker() as db:
            panel = await db.get(Panel, panel_id)
            if not panel:
                return
            db.add(
                PanelMessage(
                    panel_id=panel_id,
                    speaker=speaker,
                    persona_id=persona_id,
                    content=content.strip(),
                )
            )
            # Touch updated_at so recently-used panels sort first in the hub.
            panel.updated_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as e:  # never let persistence kill the live session
        logger.error(f"Failed to persist panel message for {panel_id}: {e}")
