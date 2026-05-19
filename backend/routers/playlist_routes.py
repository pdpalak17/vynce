"""
JamSync Playlist Routes — CRUD for user playlists.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import Playlist, User
from ..schemas import PlaylistCreate, PlaylistResponse, PlaylistUpdate

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


@router.get("/", response_model=list[PlaylistResponse])
async def list_playlists(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all playlists for the current user."""
    result = await db.execute(
        select(Playlist)
        .where(Playlist.owner_id == user.id)
        .order_by(Playlist.created_at.desc())
    )
    return [PlaylistResponse.model_validate(p) for p in result.scalars().all()]


@router.post("/", response_model=PlaylistResponse, status_code=status.HTTP_201_CREATED)
async def create_playlist(
    payload: PlaylistCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new playlist."""
    playlist = Playlist(
        name=payload.name,
        owner_id=user.id,
        tracks="[]",
    )
    db.add(playlist)
    await db.commit()
    await db.refresh(playlist)
    return PlaylistResponse.model_validate(playlist)


@router.put("/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist(
    playlist_id: str,
    payload: PlaylistUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update playlist name or tracks."""
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id))
    playlist = result.scalar_one_or_none()

    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if playlist.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not playlist owner")

    if payload.name is not None:
        playlist.name = payload.name
    if payload.tracks is not None:
        playlist.tracks = json.dumps(payload.tracks)

    await db.commit()
    await db.refresh(playlist)
    return PlaylistResponse.model_validate(playlist)


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(
    playlist_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a playlist."""
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id))
    playlist = result.scalar_one_or_none()

    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if playlist.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not playlist owner")

    await db.delete(playlist)
    await db.commit()
