"""
Vynce JioSaavn Service — Async client for JioSaavn API.
Provides access to Bollywood, Hindi, and Indian music catalog.
Uses the local jiosaavnpy library directly.
"""

import logging
from typing import Optional
import anyio
import asyncio
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
        # Patch HOME_DETAILS_URL to use web6dot0 context so that new_trending and new_albums are returned
        _jio.endpoints.HOME_DETAILS_URL = _jio.endpoints.HOME_DETAILS_URL.replace("ctx=wap6dot0", "ctx=web6dot0")
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
    import random
    jio = get_jio()
    tracks = []
    seen_ids = set()
    
    try:
        # Lowercase language is crucial because getLaunchData is case-sensitive for new_trending
        lang_lower = language.lower().strip()
        home_data = await anyio.to_thread.run_sync(jio.get_home, lang_lower)
        
        # 1. Extract tracks of type="song" from now_trending
        now_trending = home_data.get("now_trending", [])
        for item in now_trending:
            if isinstance(item, dict) and item.get("track_id"):
                track = _parse_track(item)
                if track["id"] not in seen_ids:
                    seen_ids.add(track["id"])
                    tracks.append(track)
                    
        # 2. If we need more tracks, fetch them from the top charts playlists returned on home page
        if len(tracks) < limit:
            charts = home_data.get("top_charts", [])
            playlist_tasks = []
            for c in charts[:2]:
                pid = c.get("playlist_id")
                if pid:
                    playlist_tasks.append(anyio.to_thread.run_sync(jio.playlist_info, pid))
            if playlist_tasks:
                playlist_results = await asyncio.gather(*playlist_tasks, return_exceptions=True)
                for playlist_res in playlist_results:
                    if not isinstance(playlist_res, Exception) and playlist_res.get("tracks"):
                        for song in playlist_res["tracks"]:
                            track = _parse_track(song)
                            if track["id"] not in seen_ids:
                                seen_ids.add(track["id"])
                                tracks.append(track)
    except Exception as e:
        logger.warning(f"JioSaavn get_home failed: {e}. Falling back to search.")

    if len(tracks) < limit:
        # Fallback: search popular latest songs
        try:
            query = f"Latest {language} Songs" if language.lower() in ["hindi", "punjabi", "tamil", "telugu"] else "Latest Hits"
            results = await anyio.to_thread.run_sync(jio.search_songs, query, limit * 2)
            for t in results:
                track = _parse_track(t)
                if track["id"] not in seen_ids:
                    seen_ids.add(track["id"])
                    tracks.append(track)
        except Exception as ex:
            logger.error(f"JioSaavn trending fallback search error: {ex}")

    # Shuffle to introduce dynamic variation on each call
    random.shuffle(tracks)

    return {
        "tracks": tracks[:limit],
        "total": len(tracks[:limit]),
        "source": "jiosaavn",
    }


async def get_new_releases(limit: int = 20, language: str = "hindi") -> dict:
    """Get new releases from JioSaavn homepage new albums."""
    import random
    jio = get_jio()
    tracks = []
    seen_ids = set()
    
    try:
        lang_lower = language.lower().strip()
        home_data = await anyio.to_thread.run_sync(jio.get_home, lang_lower)
        albums = home_data.get("new_albums", [])
        
        # Concurrently fetch tracks from the top 6 new albums
        album_tasks = []
        for a in albums[:6]:
            album_id = a.get("album_id")
            if album_id:
                album_tasks.append(get_album_tracks(album_id))
                
        if album_tasks:
            album_results = await asyncio.gather(*album_tasks, return_exceptions=True)
            for album_res in album_results:
                if not isinstance(album_res, Exception) and album_res.get("tracks"):
                    for t in album_res["tracks"]:
                        if t["id"] not in seen_ids:
                            seen_ids.add(t["id"])
                            tracks.append(t)
    except Exception as e:
        logger.warning(f"Error fetching new releases from homepage: {e}")

    # Fallback to search if we didn't get enough tracks
    if len(tracks) < limit:
        try:
            query = f"New {language} Releases" if language.lower() in ["hindi", "punjabi", "tamil", "telugu"] else "New Releases"
            search_res = await search_tracks(query, limit=limit * 2)
            for t in search_res.get("tracks", []):
                if t["id"] not in seen_ids:
                    seen_ids.add(t["id"])
                    tracks.append(t)
        except Exception as ex:
            logger.error(f"New releases fallback search error: {ex}")

    # Shuffle to ensure freshness on every page load
    random.shuffle(tracks)
    
    return {
        "tracks": tracks[:limit],
        "total": len(tracks[:limit]),
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


def extract_title_keywords(title: str) -> str:
    """Extract clean keywords from song title for searching related tracks."""
    import re
    # Remove contents in parentheses or brackets
    clean_title = re.sub(r'[\(\[][^\)\]]*[\)\]]', '', title)
    # Remove special characters
    clean_title = re.sub(r'[^a-zA-Z0-9\s]', '', clean_title)
    # Keep words longer than 2 characters
    words = [w for w in clean_title.split() if len(w) > 2]
    # Return first 3 keywords joined by space
    return " ".join(words[:3])


async def get_similar_tracks(song_id: str, limit: int = 10) -> dict:
    """Get similar tracks for a song, preferring same album, artist, and language."""
    import re
    import random
    jio = get_jio()
    
    # 1. Get original song details
    song_info = await get_song_details(song_id)
    if not song_info:
        # Fall back to trending if song info could not be fetched
        trending_res = await get_trending(limit=limit)
        return trending_res
        
    original_title = song_info.get("title", "")
    original_language = song_info.get("language", "").strip().lower()
    original_emotion = detect_emotion(original_title)
    original_artists = []
    original_album = song_info.get("album", "")
    
    if song_info.get("artist"):
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
    pool_artists = []
    pool_title_search = []
    pool_trending = []

    # A. Native similar_songs (just in case)
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

    # C. Artists (Concurrently fetch tracks for up to 2 artists)
    artist_tasks = []
    for artist_name in original_artists[:2]:
        artist_tasks.append(search_tracks(artist_name, limit=15))
    if artist_tasks:
        artist_results = await asyncio.gather(*artist_tasks, return_exceptions=True)
        for search_res in artist_results:
            if not isinstance(search_res, Exception) and search_res.get("tracks"):
                pool_artists.extend(search_res["tracks"])

    # D. Title Keywords Search
    title_keywords = extract_title_keywords(original_title)
    if title_keywords:
        try:
            search_res = await search_tracks(title_keywords, limit=15)
            pool_title_search = search_res.get("tracks", [])
        except Exception as e:
            logger.warning(f"Failed to search title keywords '{title_keywords}': {e}")

    # E. Trending (Used as low priority fallback filler)
    try:
        trending_res = await get_trending(limit=20, language=original_language if original_language else "hindi")
        pool_trending = trending_res.get("tracks", [])
    except Exception as e:
        logger.warning(f"Failed to get trending for similarity fallback: {e}")

    # 3. Score and Filter candidates
    similar_ids = {t["id"] for t in pool_similar if "id" in t}
    album_ids = {t["id"] for t in pool_album if "id" in t}
    artist_ids = {t["id"] for t in pool_artists if "id" in t}
    title_search_ids = {t["id"] for t in pool_title_search if "id" in t}
    
    all_candidates = []
    seen_ids = {song_id}
    seen_titles = [original_title]
    
    for t in (pool_similar + pool_album + pool_artists + pool_title_search + pool_trending):
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
                all_candidates.append(t)

    scored_tracks = []
    for t in all_candidates:
        cand_lang = t.get("language", "").strip().lower()
        title = t.get("title", "")
        
        # Strict language matching
        if original_language and cand_lang and cand_lang != original_language:
            continue
            
        score = 0.0
        
        if t["id"] in similar_ids:
            score += 8.0
        if t["id"] in album_ids:
            score += 5.0
        if t["id"] in artist_ids:
            score += 3.0
        if t["id"] in title_search_ids:
            score += 2.0
            
        if original_language and cand_lang == original_language:
            score += 2.0
            
        candidate_emotion = detect_emotion(title)
        if candidate_emotion == original_emotion and original_emotion != "neutral":
            score += 0.5
            
        score += random.uniform(-0.1, 0.1)
        
        scored_tracks.append((score, t))

    scored_tracks.sort(key=lambda x: x[0], reverse=True)
    final_tracks = [item[1] for item in scored_tracks]

    return {
        "tracks": final_tracks[:limit],
        "total": len(final_tracks[:limit]),
        "source": "jiosaavn"
    }


async def get_artist_details(artist_id: str, song_limit: int = 20, album_limit: int = 10) -> dict:
    """Fetch top songs and albums for a specific artist."""
    jio = get_jio()
    try:
        results = await anyio.to_thread.run_sync(jio.artist_info, artist_id, song_limit, album_limit)
        if results and isinstance(results, list) and len(results) > 0:
            info = results[0]
            top_songs = [_parse_track(s) for s in info.get("top_songs", [])]
            
            thumbnails = info.get("thumbnails") or {}
            quality = thumbnails.get("quality") or {}
            art = quality.get("500x500") or quality.get("150x150") or ""
            
            top_albums = []
            for a in info.get("top_albums", []):
                album_thumbnails = a.get("thumbnails") or {}
                album_quality = album_thumbnails.get("quality") or {}
                album_art = album_quality.get("150x150") or album_quality.get("500x500") or ""
                top_albums.append({
                    "id": a.get("album_id", ""),
                    "name": a.get("title", "Unknown Album"),
                    "artist": a.get("primary_artists") or "Unknown Artist",
                    "art": album_art,
                    "year": a.get("release_year", ""),
                    "song_count": int(a.get("track_count", 0) or 0),
                    "language": a.get("album_language", ""),
                })
            
            return {
                "id": info.get("artist_id", ""),
                "name": info.get("name", "Unknown Artist"),
                "subtitle": info.get("subtitle", ""),
                "role": info.get("role", "artist"),
                "art": art,
                "top_songs": top_songs,
                "top_albums": top_albums,
            }
        return {}
    except Exception as e:
        logger.error(f"JioSaavn artist info error: {e}")
        return {}


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

