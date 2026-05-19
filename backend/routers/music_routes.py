"""
JamSync Music Routes — Search, trending, albums, and song details.
Uses JioSaavn (primary) for Bollywood + Jamendo (secondary) for CC music.
"""

from fastapi import APIRouter, Depends, Query

from ..auth import get_current_user
from ..models import User
from ..services import jiosaavn, jamendo

router = APIRouter(prefix="/api/music", tags=["music"])


@router.get("/search")
async def search_music(
    q: str = Query(..., min_length=1, description="Search query"),
    source: str = Query("all", description="Music source: jiosaavn, jamendo, or all"),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """Search for music tracks. JioSaavn is primary (Bollywood + all Indian music)."""
    if source == "jamendo":
        return await jamendo.search_tracks(q, limit=limit)
    elif source == "jiosaavn":
        return await jiosaavn.search_tracks(q, limit=limit)
    else:
        # Search JioSaavn first (has Bollywood), fall back to Jamendo
        result = await jiosaavn.search_tracks(q, limit=limit)
        if result.get("tracks"):
            return result
        return await jamendo.search_tracks(q, limit=limit)


@router.get("/trending")
async def get_trending(
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """Get trending Bollywood tracks."""
    return await jiosaavn.get_trending(limit=limit)


@router.get("/albums/search")
async def search_albums(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=30),
    user: User = Depends(get_current_user),
):
    """Search for albums."""
    return await jiosaavn.search_albums(q, limit=limit)


@router.get("/albums/{album_id}")
async def get_album(
    album_id: str,
    user: User = Depends(get_current_user),
):
    """Get album details and all tracks."""
    return await jiosaavn.get_album_tracks(album_id)


@router.get("/song/{song_id}")
async def get_song(
    song_id: str,
    user: User = Depends(get_current_user),
):
    """Get song details with stream URL."""
    return await jiosaavn.get_song_details(song_id)


@router.get("/song/{song_id}/similar")
async def get_similar_songs(
    song_id: str,
    limit: int = Query(10, ge=1, le=30),
    user: User = Depends(get_current_user),
):
    """Get similar or recommended tracks for auto-play."""
    return await jiosaavn.get_similar_tracks(song_id, limit=limit)


@router.get("/genres")
async def get_genres(user: User = Depends(get_current_user)):
    """Get available genre categories."""
    return {"genres": [
        "Bollywood", "Hindi Pop", "Romantic", "Sad Songs", "Party",
        "Devotional", "Ghazal", "Punjabi", "Tamil", "Telugu",
        "90s Bollywood", "2000s Bollywood", "Indie", "Sufi",
        "Hip Hop", "EDM", "Classical", "Rock", "Pop", "Lo-fi",
    ]}


@router.get("/genre/{genre}")
async def get_by_genre(
    genre: str,
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """Get tracks by genre — searches JioSaavn with genre as query."""
    return await jiosaavn.search_tracks(f"{genre} songs", limit=limit)
