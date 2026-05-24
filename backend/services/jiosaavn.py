"""
Vynce JioSaavn Service — Async client for JioSaavn API.
Provides access to Bollywood, Hindi, and Indian music catalog.
Uses the local jiosaavnpy library directly.
"""

import logging
from typing import Optional
import anyio
from jiosaavnpy import JioSaavn

logger = logging.getLogger(__name__)

_jio: Optional[JioSaavn] = None


def get_jio() -> JioSaavn:
    global _jio
    if _jio is None:
        _jio = JioSaavn()
        indian_ip = "103.241.136.1"
        _jio.requests.headers.update({
            "X-Forwarded-For": indian_ip,
            "X-Real-IP": indian_ip,
            "Client-IP": indian_ip,
            "Accept-Language": "en-US,en;q=0.9",
        })
    return _jio


def _parse_track(t: dict) -> dict:
    """Parse a JioSaavn track from jiosaavnpy into our standard format."""
    thumbnails = t.get("thumbnails") or {}
    quality = thumbnails.get("quality") or {}
    album_art = quality.get("500x500") or quality.get("150x150") or quality.get("50x50") or ""

    stream_urls = t.get("stream_urls") or {}
    stream_url = (
        stream_urls.get("very_high_quality") or
        stream_urls.get("high_quality") or
        stream_urls.get("medium_quality") or
        stream_urls.get("low_quality") or
        ""
    )

    try:
        duration = int(t.get("duration", 0))
    except (ValueError, TypeError):
        duration = 0

    return {
        "id": t.get("track_id", ""),
        "title": t.get("title", "Unknown"),
        "artist": t.get("primary_artists") or t.get("artist") or "Unknown Artist",
        "album": t.get("album_name", ""),
        "album_art": album_art,
        "stream_url": stream_url,
        "duration": duration,
        "year": t.get("release_year", ""),
        "language": t.get("track_language", ""),
        "source": "jiosaavn",
    }


async def search_tracks(query: str, limit: int = 20) -> dict:
    """Search JioSaavn for tracks."""
    jio = get_jio()
    try:
        results = await anyio.to_thread.run_sync(jio.search_songs, query, limit)
        tracks = [_parse_track(t) for t in results]
        return {
            "tracks": tracks,
            "total": len(tracks),
            "source": "jiosaavn",
        }
    except Exception as e:
        logger.error(f"JioSaavn search error: {e}")
        return {"tracks": [], "total": 0, "source": "jiosaavn"}


async def search_albums(query: str, limit: int = 10) -> dict:
    """Search JioSaavn for albums."""
    jio = get_jio()
    try:
        results = await anyio.to_thread.run_sync(jio.search_albums, query, limit)
        albums = []
        for a in results:
            thumbnails = a.get("thumbnails") or {}
            quality = thumbnails.get("quality") or {}
            art = quality.get("150x150") or quality.get("500x500") or ""
            albums.append({
                "id": a.get("album_id", ""),
                "name": a.get("title", "Unknown Album"),
                "artist": a.get("artists") or "Unknown Artist",
                "art": art,
                "year": a.get("release_year", ""),
                "song_count": int(a.get("track_count", 0) or 0),
                "language": a.get("album_language", ""),
            })
        return {"albums": albums, "total": len(albums)}
    except Exception as e:
        logger.error(f"JioSaavn album search error: {e}")
        return {"albums": [], "total": 0}


async def get_album_tracks(album_id: str) -> dict:
    """Get all tracks from a JioSaavn album."""
    jio = get_jio()
    try:
        album_data = await anyio.to_thread.run_sync(jio.album_info, album_id)
        songs = album_data.get("tracks", [])
        tracks = [_parse_track(s) for s in songs]

        thumbnails = album_data.get("thumbnails") or {}
        quality = thumbnails.get("quality") or {}
        art = quality.get("500x500") or quality.get("150x150") or ""

        return {
            "id": album_data.get("album_id", album_id),
            "name": album_data.get("title", ""),
            "artist": album_data.get("primary_artists", ""),
            "art": art,
            "year": album_data.get("release_date", "")[:4] if album_data.get("release_date") else "",
            "tracks": tracks,
            "total": len(tracks),
        }
    except Exception as e:
        logger.error(f"JioSaavn album tracks error: {e}")
        return {"tracks": [], "total": 0}


async def get_trending(limit: int = 20, language: str = "hindi") -> dict:
    """Get trending songs from JioSaavn."""
    jio = get_jio()
    tracks = []
    try:
        lang_capitalized = language.capitalize()
        home_data = await anyio.to_thread.run_sync(jio.get_home, lang_capitalized)
        now_trending = home_data.get("now_trending", [])
        for item in now_trending:
            if isinstance(item, dict) and item.get("track_id"):
                tracks.append(_parse_track(item))
                if len(tracks) >= limit:
                    break
    except Exception as e:
        logger.warning(f"JioSaavn get_home failed: {e}. Falling back to search.")

    if not tracks:
        # Fallback: search popular Hindi songs
        try:
            query = "Latest Hindi Songs" if language.lower() == "hindi" else "Latest Hits"
            results = await anyio.to_thread.run_sync(jio.search_songs, query, limit)
            tracks = [_parse_track(t) for t in results]
        except Exception as ex:
            logger.error(f"JioSaavn trending fallback error: {ex}")

    return {
        "tracks": tracks,
        "total": len(tracks),
        "source": "jiosaavn",
    }


async def get_song_details(song_id: str) -> dict:
    """Get full details + stream URL for a specific song."""
    jio = get_jio()
    try:
        song_data = await anyio.to_thread.run_sync(jio.song_info, song_id)
        if song_data:
            return _parse_track(song_data)
        return {}
    except Exception as e:
        logger.error(f"JioSaavn song details error: {e}")
        return {}


ROMANTIC_KEYWORDS = [
    "love", "dil", "pyar", "pyaar", "ishq", "mohabbat", "romantic", "dhadkan", "humsafar", "sanam", "tum", "romance", 
    "sajne", "chaahat", "jaanam", "shiddat", "pehl", "jahan", "rabba", "khuda", "soniye", "heeriye", "ranjha", "jodi", 
    "dhak", "nayan", "naina", "aankh", "mehboob", "janam", "ibadat", "aashiqui", "piya", "jiya", "saibo", "mann", "chahe",
    "bana le", "rang", "aankhein", "baatein", "raatein", "sath", "saath", "jaan", "baho", "baahon", "chahe", "naseeb"
]
SAD_KEYWORDS = [
    "sad", "dard", "tanhai", "judai", "rona", "khamoshi", "breakup", "broken", "bewafa", "zindagi", "dukh", "rua", 
    "aansoo", "gum", "alvida", "judaiyaan", "faasle", "dhoke", "tuta", "toota", "akela", "asoon", "aansu", "rula", "tanha", "maula"
]
PARTY_KEYWORDS = [
    "party", "dance", "club", "dj", "nach", "dhamaka", "hangover", "groove", "sharab", "nasha", "daaru", "daru", 
    "thumka", "bhangra", "beat", "bass", "peene", "high", "suroor", "masti", "sharaabi", "duniya", "sharaab", "daru", "glass"
]

def detect_emotion(title: str) -> str:
    t = title.lower()
    for kw in SAD_KEYWORDS:
        if kw in t:
            return "sad"
    for kw in PARTY_KEYWORDS:
        if kw in t:
            return "party"
    for kw in ROMANTIC_KEYWORDS:
        if kw in t:
            return "romantic"
    return "neutral"


async def get_similar_tracks(song_id: str, limit: int = 10) -> dict:
    """Get similar tracks for a song, preferring same language and same emotion."""
    import re
    jio = get_jio()
    
    # 1. Get original song details
    song_info = await get_song_details(song_id)
    original_title = song_info.get("title", "") if song_info else ""
    original_language = song_info.get("language", "").strip().lower() if song_info else ""
    original_emotion = detect_emotion(original_title) if original_title else "neutral"
    original_artists = []
    original_album = song_info.get("album", "") if song_info else ""
    
    if song_info and song_info.get("artist"):
        artists_str = song_info["artist"]
        for part in re.split(r'[,&]|\bfeat\b', artists_str):
            name = part.strip()
            if name and name != "Unknown Artist":
                original_artists.append(name)

    def is_same_song(title1: str, title2: str) -> bool:
        if not title1 or not title2:
            return False
        
        def clean_title(t: str) -> str:
            t = t.lower()
            t = re.sub(r'[\(\[][^\)\]]*[\)\]]', '', t)
            t = re.sub(r'[^a-z0-9\s]', '', t)
            return t.strip()

        t1_clean = clean_title(title1)
        t2_clean = clean_title(title2)
        
        if t1_clean == t2_clean:
            return True
            
        longer, shorter = (t1_clean, t2_clean) if len(t1_clean) > len(t2_clean) else (t2_clean, t1_clean)
        
        if shorter in longer:
            version_words = ["remix", "reprise", "acoustic", "lofi", "unplugged", "cover", "version", "sad", "female", "male", "mashup", "mix", "lullaby", "instrumental", "slowed", "reverb", "bgm", "theme"]
            extra_part = longer.replace(shorter, "").strip()
            if any(w in extra_part for w in version_words):
                return True
                
        return False

    # 2. Gather candidate pools
    pool_similar = []
    pool_album = []
    pool_artists = {}
    pool_trending = []

    # A. Native similar_songs
    try:
        results = await anyio.to_thread.run_sync(jio.similar_songs, song_id)
        if results:
            pool_similar = [_parse_track(t) for t in results]
    except Exception as e:
        logger.warning(f"JioSaavn similar_songs failed: {e}")

    # B. Same Album
    if original_album and original_album.lower().strip() != original_title.lower().strip():
        try:
            album_search = await search_albums(original_album, limit=1)
            albums = album_search.get("albums", [])
            if albums:
                album_id = albums[0]["id"]
                album_res = await get_album_tracks(album_id)
                pool_album = album_res.get("tracks", [])
        except Exception as e:
            logger.warning(f"Failed to get album tracks: {e}")

    # C. Artists
    for artist_name in original_artists[:3]:
        try:
            search_res = await search_tracks(artist_name, limit=15)
            tracks = search_res.get("tracks", [])
            if tracks:
                pool_artists[artist_name] = tracks
        except Exception as e:
            logger.warning(f"Failed to search artist '{artist_name}': {e}")

    # D. Trending
    try:
        trending_res = await get_trending(limit=30, language=original_language if original_language else "hindi")
        pool_trending = trending_res.get("tracks", [])
    except Exception as e:
        logger.warning(f"Failed to get trending: {e}")

    # 3. Interleave candidates
    candidates = []
    
    max_iterations = max(
        len(pool_similar),
        len(pool_album),
        sum(len(v) for v in pool_artists.values()),
        len(pool_trending)
    )
    
    similar_idx = 0
    album_idx = 0
    artist_indices = {name: 0 for name in pool_artists}
    trending_idx = 0
    
    for _ in range(max_iterations):
        added = False
        
        if similar_idx < len(pool_similar):
            candidates.append(pool_similar[similar_idx])
            similar_idx += 1
            added = True
            
        if album_idx < len(pool_album):
            candidates.append(pool_album[album_idx])
            album_idx += 1
            added = True
            
        for name in pool_artists:
            idx = artist_indices[name]
            if idx < len(pool_artists[name]):
                candidates.append(pool_artists[name][idx])
                artist_indices[name] = idx + 1
                added = True
                
        if trending_idx < len(pool_trending):
            candidates.append(pool_trending[trending_idx])
            trending_idx += 1
            added = True
            
        if not added:
            break

    # 4. Deduplicate and exclude
    seen_ids = {song_id}
    seen_titles = [original_title]
    unique_candidates = []
    for t in candidates:
        track_id = t.get("id")
        title = t.get("title", "")
        if track_id and track_id not in seen_ids:
            is_dup = False
            for seen_title in seen_titles:
                if is_same_song(seen_title, title):
                    is_dup = True
                    break
            if not is_dup:
                seen_ids.add(track_id)
                seen_titles.append(title)
                unique_candidates.append(t)

    # 5. Filter and Score
    filtered_scored_tracks = []
    for t in unique_candidates:
        lang = t.get("language", "").strip().lower()
        title = t.get("title", "")
        
        if original_language and lang and lang != original_language:
            continue
            
        candidate_emotion = detect_emotion(title)
        
        score = 0
        if candidate_emotion == original_emotion and original_emotion != "neutral":
            score = 3
        elif original_emotion == "neutral" or candidate_emotion == "neutral":
            score = 2
        else:
            score = 1
            
        filtered_scored_tracks.append((score, t))

    filtered_scored_tracks.sort(key=lambda x: x[0], reverse=True)
    final_tracks = [item[1] for item in filtered_scored_tracks]

    return {
        "tracks": final_tracks[:limit],
        "total": len(final_tracks[:limit]),
        "source": "jiosaavn"
    }


async def get_lyrics(song_id: str) -> Optional[str]:
    """Fetch lyrics for a song from JioSaavn."""
    jio = get_jio()
    try:
        url = "https://www.jiosaavn.com/api.php"
        params = {
            "__call": "lyrics.getLyrics",
            "ctx": "web6dot0",
            "api_version": "4",
            "_format": "json",
            "_marker": "0",
            "lyrics_id": song_id
        }
        response = await anyio.to_thread.run_sync(
            lambda: jio.requests.get(url, params=params).json()
        )
        if response and "lyrics" in response:
            return response["lyrics"]
    except Exception as e:
        logger.error(f"Error fetching lyrics for {song_id}: {e}")
    return None


async def close():
    """Close the client (no-op for jiosaavnpy)."""
    pass

