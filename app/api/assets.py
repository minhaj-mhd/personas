import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Asset

router = APIRouter(prefix="/api/assets", tags=["Assets"])


@router.get("/{asset_id}")
async def get_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Serve an asset's raw bytes with its stored MIME type (used by <img> previews
    and by the server when injecting the image into a live session)."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )
    return Response(
        content=asset.data,
        media_type=asset.mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a single uploaded asset."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found"
        )
    await db.delete(asset)
    await db.commit()
    return
