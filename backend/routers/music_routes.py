"""
Vynce Music Routes — Search, trending, albums, and song details.
Uses JioSaavn (primary) for Bollywood + Jamendo (secondary) for CC music.
"""

import asyncio
import random
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, delete, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import User, LikedSong, DislikedSong, UserHistory, CoPlay, DailyMix
from ..schemas import (
    LikedSongCreate, LikedSongResponse,
    UserHistoryCreate, UserHistoryResponse,
    HomeSectionResponse
)
from ..services import jiosaavn, jamendo
from ..services.recommender import recommend_tracks

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


def get_user_genres_from_history(history_list: list, liked_list: list) -> list:
    import random
    detected = set()
    all_items = history_list + liked_list
    for item in all_items:
        title = (item.get("track_title") or item.get("title") or "").lower()
        artist = (item.get("track_artist") or item.get("artist") or "").lower()
        
        if any(kw in title for kw in ["love", "romantic", "pyar", "dil", "ishq", "sanam"]):
            detected.add("romantic hindi")
        if any(kw in title for kw in ["sad", "judai", "dard", "tuta", "rua"]):
            detected.add("sad hindi songs")
        if any(kw in title for kw in ["party", "dance", "club", "dj", "nach"]):
            detected.add("hindi party dance")
        if any(kw in title or kw in artist for kw in ["punjabi", "singh", "dhillon", "sidhu", "diljit"]):
            detected.add("punjabi")
        if "lofi" in title or "lo-fi" in title or "lofi" in artist:
            detected.add("hindi lofi")
        if "sufi" in title or "sufi" in artist or any(kw in title for kw in ["maula", "khuda", "ali"]):
            detected.add("sufi")
        if any(kw in title or kw in artist for kw in ["90s", "classic", "old", "kishore", "lata", "rafi"]):
            detected.add("90s bollywood")

    fallback_genres = ["romantic hindi", "sad hindi songs", "hindi party dance", "hindi lofi", "punjabi", "sufi", "90s bollywood"]
    detected_list = list(detected)
    random.shuffle(detected_list)
    
    for g in fallback_genres:
        if len(detected_list) >= 4:
            break
        if g not in detected_list:
            detected_list.append(g)
            
    random.shuffle(detected_list)
    return detected_list[:4]


@router.get("/home", response_model=list[HomeSectionResponse])
async def get_home_page(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch homepage categories with dynamically seeded candidate pools and MLP recommendations."""
    # Retrieve user's listening history & liked/disliked songs
    try:
        history_result = await db.execute(
            select(UserHistory).where(UserHistory.user_id == user.id).order_by(desc(UserHistory.played_at)).limit(50)
        )
        history_songs = history_result.scalars().all()
        history_list = [{"track_id": s.track_id, "track_title": s.track_title, "track_artist": s.track_artist} for s in history_songs]
        
        liked_result = await db.execute(
            select(LikedSong).where(LikedSong.user_id == user.id)
        )
        liked_songs = liked_result.scalars().all()
        liked_list = [{"track_id": s.track_id, "track_title": s.track_title, "track_artist": s.track_artist} for s in liked_songs]
        
        disliked_result = await db.execute(
            select(DislikedSong).where(DislikedSong.user_id == user.id)
        )
        disliked_ids = {s.track_id for s in disliked_result.scalars().all()}
    except Exception as e:
        print(f"[Recommender-DB] Error querying user history: {e}")
        history_list = []
        liked_list = []
        disliked_ids = set()

    # Dynamic Seeding: pick 3 seed queries from recent history or fallback
    seed_queries = []
    if history_list or liked_list:
        candidates = []
        for t in liked_list:
            if t.get("track_artist") and t["track_artist"] not in candidates:
                candidates.append(t["track_artist"])
        for t in history_list:
            if t.get("track_artist") and t["track_artist"] not in candidates:
                candidates.append(t["track_artist"])
            if t.get("track_title") and t["track_title"] not in candidates:
                candidates.append(t["track_title"])
        if candidates:
            random.shuffle(candidates)
            seed_queries = candidates[:3]

    # Fallbacks if seeds are empty
    while len(seed_queries) < 3:
        fallback = random.choice([
            "Arijit Singh", "Pritam", "AR Rahman", "Bollywood Hits", 
            "Punjabi Songs", "Hindi Lofi", "Sufi", "90s Bollywood"
        ])
        if fallback not in seed_queries:
            seed_queries.append(fallback)

    # Dynamic Seeding from history genres/moods
    user_genres = get_user_genres_from_history(history_list, liked_list)

    # Standard sections + Seeded sections
    tasks = [
        jiosaavn.get_trending(limit=15, language="hindi"),
        jiosaavn.search_tracks("romantic hindi", limit=15),
        jiosaavn.search_tracks("sad hindi songs", limit=15),
        jiosaavn.search_tracks("hindi party dance", limit=15),
        jiosaavn.get_new_releases(limit=30, language="hindi"),
    ]
    for sq in seed_queries:
        tasks.append(jiosaavn.search_tracks(sq, limit=12))
    for ug in user_genres:
        tasks.append(jiosaavn.search_tracks(ug, limit=12))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    trending = results[0] if not isinstance(results[0], Exception) else {"tracks": []}
    romantic = results[1] if not isinstance(results[1], Exception) else {"tracks": []}
    sad = results[2] if not isinstance(results[2], Exception) else {"tracks": []}
    party = results[3] if not isinstance(results[3], Exception) else {"tracks": []}
    new_releases = results[4] if not isinstance(results[4], Exception) else {"tracks": []}
    
    # Collect candidate pool from all sections to run recommendation scoring
    all_tracks = []
    # Mix in tasks from results 0-3 and the custom history/genre search tasks (index 5 onwards)
    # We do NOT mix the raw new_releases directly into general MLP scoring to avoid duplicates
    for idx, r in enumerate(results):
        if idx != 4 and not isinstance(r, Exception) and r.get("tracks"):
            all_tracks.extend(r["tracks"])
    
    seen_ids = set()
    unique_tracks = []
    for t in all_tracks:
        if t["id"] not in seen_ids:
            seen_ids.add(t["id"])
            unique_tracks.append(t)

    # Retrieve co-play weights for recommendation boosting
    co_play_weights = {}
    if history_list:
        try:
            recent_ids = [t["track_id"] for t in history_list[:5]]
            coplay_result = await db.execute(
                select(CoPlay.song_b_id, func.count(CoPlay.id))
                .where(CoPlay.song_a_id.in_(recent_ids))
                .group_by(CoPlay.song_b_id)
            )
            coplays = coplay_result.all()
            if coplays:
                max_cnt = max(item[1] for item in coplays)
                for song_b_id, count in coplays:
                    co_play_weights[song_b_id] = count / max_cnt
        except Exception as ex:
            print(f"[Recommender-CoPlay] Error fetching co-play weights: {ex}")

    # Get personalized For You tracks using the neural network
    # We only need the top 4 tracks for Hero Banner and Top Charts
    personalized_candidates = recommend_tracks(
        history_tracks=history_list,
        liked_tracks=liked_list,
        disliked_ids=disliked_ids,
        candidate_tracks=unique_tracks,
        co_play_weights=co_play_weights,
        limit=4
    )
    
    # Shuffle new releases and filter out disliked
    fresh_releases = [t for t in new_releases.get("tracks", []) if t["id"] not in disliked_ids]
    random.shuffle(fresh_releases)
    
    # Combine: First 4 are personalized, followed by dynamic new releases
    for_you = personalized_candidates + fresh_releases
    
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


@router.get("/artists/search")
async def search_artists(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=30),
    user: User = Depends(get_current_user),
):
    """Search for artists."""
    jio = jiosaavn.get_jio()
    try:
        results = await anyio.to_thread.run_sync(jio.search_artists, q, limit)
        return {"artists": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/artist/{artist_id}")
async def get_artist_page(
    artist_id: str,
    user: User = Depends(get_current_user),
):
    """Get artist detail page."""
    details = await jiosaavn.get_artist_details(artist_id)
    if not details:
        raise HTTPException(status_code=404, detail="Artist not found")
    return details


@router.get("/daily-mix")
async def get_daily_mix(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve or generate daily mix for the user."""
    import json
    import datetime
    
    # Check if a mix was already generated today
    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        existing_result = await db.execute(
            select(DailyMix)
            .where(DailyMix.user_id == user.id)
            .where(DailyMix.generated_at >= today_start)
            .order_by(desc(DailyMix.generated_at))
            .limit(1)
        )
        existing_mix = existing_result.scalar_one_or_none()
        if existing_mix:
            return {"title": "Daily Mix", "tracks": json.loads(existing_mix.tracks)}
    except Exception as e:
        print(f"[DailyMix] Error checking existing mix: {e}")

    # Generate a new mix
    # Get user history and liked songs
    history_result = await db.execute(
        select(UserHistory).where(UserHistory.user_id == user.id).order_by(desc(UserHistory.played_at)).limit(50)
    )
    history_songs = history_result.scalars().all()
    
    liked_result = await db.execute(
        select(LikedSong).where(LikedSong.user_id == user.id)
    )
    liked_songs = liked_result.scalars().all()
    
    seeds = []
    for s in liked_songs:
        if s.track_artist not in seeds:
            seeds.append(s.track_artist)
    for s in history_songs:
        if s.track_artist not in seeds:
            seeds.append(s.track_artist)
            
    if not seeds:
        seeds = ["Arijit Singh", "Pritam", "AR Rahman"]
    
    random.shuffle(seeds)
    selected_seeds = seeds[:3]
    
    mix_tracks = []
    seen_ids = set()
    
    # Fetch songs from seeds
    for seed in selected_seeds:
        try:
            res = await jiosaavn.search_tracks(seed, limit=15)
            for t in res.get("tracks", []):
                if t["id"] not in seen_ids:
                    seen_ids.add(t["id"])
                    t["recommendation_reason"] = f"Inspired by {seed}"
                    mix_tracks.append(t)
        except Exception as e:
            print(f"[DailyMix] Error searching seed '{seed}': {e}")
            
    # Add some trending songs as discovery if we don't have enough
    if len(mix_tracks) < 20:
        try:
            res = await jiosaavn.get_trending(limit=15)
            for t in res.get("tracks", []):
                if t["id"] not in seen_ids:
                    seen_ids.add(t["id"])
                    t["recommendation_reason"] = "Trending choice"
                    mix_tracks.append(t)
        except Exception as e:
            print(f"[DailyMix] Error fetching trending for DailyMix: {e}")
            
    random.shuffle(mix_tracks)
    final_mix_tracks = mix_tracks[:30]
    
    # Save to database
    try:
        new_mix = DailyMix(
            user_id=user.id,
            tracks=json.dumps(final_mix_tracks)
        )
        db.add(new_mix)
        await db.commit()
    except Exception as e:
        print(f"[DailyMix] Error saving DailyMix: {e}")
        
    return {"title": "Daily Mix", "tracks": final_mix_tracks}


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
    """Add a song to user listening history and record co-play sequences."""
    import datetime
    
    # Check last played track to record co-play
    try:
        last_play_result = await db.execute(
            select(UserHistory)
            .where(UserHistory.user_id == user.id)
            .order_by(desc(UserHistory.played_at))
            .limit(1)
        )
        last_play = last_play_result.scalar_one_or_none()
        if last_play and last_play.track_id != payload.track_id:
            time_diff = datetime.datetime.utcnow() - last_play.played_at
            if time_diff.total_seconds() < 600:  # 10 minutes
                coplay = CoPlay(
                    user_id=user.id,
                    song_a_id=last_play.track_id,
                    song_b_id=payload.track_id
                )
                db.add(coplay)
    except Exception as e:
        print(f"[CoPlay] Error recording co-play: {e}")

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


@router.delete("/history/{track_id}")
async def delete_history_track(
    track_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a track or tracks with a given track_id from user's history."""
    await db.execute(
        delete(UserHistory)
        .where(UserHistory.user_id == user.id)
        .where(UserHistory.track_id == track_id)
    )
    await db.commit()
    return {"message": "Track removed from history"}


