"""
JamSync Music Routes — Search, trending, albums, and song details.
Uses JioSaavn (primary) for Bollywood + Jamendo (secondary) for CC music.
"""

import asyncio
import random
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import User, LikedSong, DislikedSong, UserHistory
from ..schemas import (
    LikedSongCreate, LikedSongResponse,
    UserHistoryCreate, UserHistoryResponse,
    HomeSectionResponse
)
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


@router.get("/home", response_model=list[HomeSectionResponse])
async def get_home_page(user: User = Depends(get_current_user)):
    """Fetch homepage categories (Trending, Romantic, Sad, Party, For You)."""
    tasks = [
        jiosaavn.get_trending(limit=12),
        jiosaavn.search_tracks("romantic hindi", limit=12),
        jiosaavn.search_tracks("sad hindi songs", limit=12),
        jiosaavn.search_tracks("hindi party dance", limit=12),
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    trending = results[0] if not isinstance(results[0], Exception) else {"tracks": []}
    romantic = results[1] if not isinstance(results[1], Exception) else {"tracks": []}
    sad = results[2] if not isinstance(results[2], Exception) else {"tracks": []}
    party = results[3] if not isinstance(results[3], Exception) else {"tracks": []}
    
    all_tracks = []
    for r in results:
        if not isinstance(r, Exception) and r.get("tracks"):
            all_tracks.extend(r["tracks"])
    
    seen_ids = set()
    unique_tracks = []
    for t in all_tracks:
        if t["id"] not in seen_ids:
            seen_ids.add(t["id"])
            unique_tracks.append(t)
    
    random.shuffle(unique_tracks)
    for_you = unique_tracks[:12]
    
    def shuffle_list(lst):
        l = list(lst)
        random.shuffle(l)
        return l
        
    return [
        {"title": "🔥 Trending Hits", "tracks": shuffle_list(trending.get("tracks", []))},
        {"title": "❤️ Romantic Hits", "tracks": shuffle_list(romantic.get("tracks", []))},
        {"title": "😢 Sad Melodies", "tracks": shuffle_list(sad.get("tracks", []))},
        {"title": "🎉 Party Anthems", "tracks": shuffle_list(party.get("tracks", []))},
        {"title": "✨ For You Mix", "tracks": for_you},
    ]


@router.get("/song/{song_id}/lyrics")
async def get_song_lyrics(song_id: str, user: User = Depends(get_current_user)):
    """Get lyrics for a track."""
    lyrics = await jiosaavn.get_lyrics(song_id)
    if not lyrics:
        return {"lyrics": "Lyrics not available for this song. Enjoy the music!"}
    return {"lyrics": lyrics}


# ── Liked Songs ───────────────────────────────────────────────────────────────

@router.post("/like", status_code=status.HTTP_201_CREATED)
async def like_song(
    payload: LikedSongCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Like a song."""
    result = await db.execute(
        select(LikedSong).where(
            LikedSong.user_id == user.id,
            LikedSong.track_id == payload.track_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {"message": "Song already liked"}

    await db.execute(
        delete(DislikedSong).where(
            DislikedSong.user_id == user.id,
            DislikedSong.track_id == payload.track_id
        )
    )

    liked = LikedSong(
        user_id=user.id,
        track_id=payload.track_id,
        track_title=payload.track_title,
        track_artist=payload.track_artist,
        track_album=payload.track_album or "",
        track_album_art=payload.track_album_art or "",
        track_stream_url=payload.track_stream_url or "",
    )
    db.add(liked)
    await db.commit()
    return {"message": "Song liked"}


@router.delete("/like/{track_id}")
async def unlike_song(
    track_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlike a song."""
    await db.execute(
        delete(LikedSong).where(
            LikedSong.user_id == user.id,
            LikedSong.track_id == track_id
        )
    )
    await db.commit()
    return {"message": "Song unliked"}


@router.get("/liked")
async def get_liked_songs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's liked songs."""
    result = await db.execute(
        select(LikedSong)
        .where(LikedSong.user_id == user.id)
        .order_by(LikedSong.liked_at.desc())
    )
    return result.scalars().all()


# ── Disliked Songs ────────────────────────────────────────────────────────────

@router.post("/dislike", status_code=status.HTTP_201_CREATED)
async def dislike_song(
    track_id: str = Query(..., description="ID of the song to dislike"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dislike a song."""
    result = await db.execute(
        select(DislikedSong).where(
            DislikedSong.user_id == user.id,
            DislikedSong.track_id == track_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {"message": "Song already disliked"}

    await db.execute(
        delete(LikedSong).where(
            LikedSong.user_id == user.id,
            LikedSong.track_id == track_id
        )
    )

    disliked = DislikedSong(
        user_id=user.id,
        track_id=track_id,
    )
    db.add(disliked)
    await db.commit()
    return {"message": "Song disliked"}


@router.delete("/dislike/{track_id}")
async def undislike_song(
    track_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Undislike a song."""
    await db.execute(
        delete(DislikedSong).where(
            DislikedSong.user_id == user.id,
            DislikedSong.track_id == track_id
        )
    )
    await db.commit()
    return {"message": "Song undisliked"}


# ── Listening History ─────────────────────────────────────────────────────────

@router.post("/history", status_code=status.HTTP_201_CREATED)
async def add_history(
    payload: UserHistoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a song to user listening history."""
    history = UserHistory(
        user_id=user.id,
        track_id=payload.track_id,
        track_title=payload.track_title,
        track_artist=payload.track_artist,
        track_album=payload.track_album or "",
        track_album_art=payload.track_album_art or "",
        track_stream_url=payload.track_stream_url or "",
    )
    db.add(history)
    await db.commit()
    return {"message": "Added to history"}


@router.get("/history")
async def get_history(
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user listening history."""
    result = await db.execute(
        select(UserHistory)
        .where(UserHistory.user_id == user.id)
        .order_by(UserHistory.played_at.desc())
        .limit(limit)
    )
    return result.scalars().all()

