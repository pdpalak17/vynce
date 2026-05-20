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


async def get_similar_tracks(song_id: str, limit: int = 10) -> dict:
    """Get similar tracks for a song, with robust fallback to artist search and title filtering."""
    import re
    jio = get_jio()
    tracks = []
    
    # Get details of current song to filter out same titles
    song_info = await get_song_details(song_id)
    original_title = song_info.get("title", "") if song_info else ""

    def is_same_song(title1: str, title2: str) -> bool:
        if not title1 or not title2:
            return False
        def get_base_title(t: str) -> str:
            t = t.lower()
            # Remove feat/ft details
            t = re.split(r'\b(feat\.?|ft\.?)\b', t)[0]
            # Split by - or | or :
            t = re.split(r'[-|:]', t)[0]
            # Remove brackets/parentheses
            t = re.sub(r'[\(\[][^\)\]]*[\)\]]', '', t)
            # Remove common version keywords
            t = re.sub(r'\b(remix|reprise|acoustic|lofi|unplugged|cover|version|sad|female|male|mashup|mix|lullaby|instrumental|slowed|reverb)\b', '', t)
            # Normalize spaces and punctuation
            t = re.sub(r'[^a-z0-9\s]', '', t)
            # Join words
            return "".join(t.split())
        
        return get_base_title(title1) == get_base_title(title2)

    # 1. Try native similar_songs
    try:
        results = await anyio.to_thread.run_sync(jio.similar_songs, song_id)
        if results:
            parsed = [_parse_track(t) for t in results]
            tracks = [
                t for t in parsed
                if t.get("id") != song_id and not is_same_song(original_title, t.get("title", ""))
            ]
    except Exception as e:
        logger.warning(f"JioSaavn similar_songs failed: {e}")

    # 2. Fallback to artist-based search if empty
    if not tracks:
        try:
            if song_info and song_info.get("artist"):
                artist = song_info["artist"]
                # Split by commas or ampersands to get primary artist
                primary_artist = artist.split(",")[0].split("&")[0].split("feat.")[0].strip()
                if primary_artist and primary_artist != "Unknown Artist":
                    search_res = await search_tracks(primary_artist, limit=limit + 5)
                    tracks = [
                        t for t in search_res.get("tracks", [])
                        if t.get("id") != song_id and not is_same_song(original_title, t.get("title", ""))
                    ]
        except Exception as e:
            logger.error(f"JioSaavn similar fallback failed: {e}")

    # 3. Fallback to trending tracks if still empty
    if not tracks:
        try:
            trending = await get_trending(limit=limit + 5)
            tracks = [
                t for t in trending.get("tracks", [])
                if t.get("id") != song_id and not is_same_song(original_title, t.get("title", ""))
            ]
        except Exception as e:
            logger.error(f"JioSaavn trending fallback failed: {e}")

    return {
        "tracks": tracks[:limit],
        "total": len(tracks[:limit]),
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

