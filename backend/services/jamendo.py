"""
Vynce Jamendo Service — Async client for the Jamendo API v3.0.
Provides free, full-length Creative Commons licensed music streaming.
"""

import logging
from typing import List, Optional

import httpx

from .. import config

logger = logging.getLogger(__name__)

# Reusable async HTTP client
_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15.0)
    return _client


async def search_tracks(
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    Search Jamendo for tracks matching a query.
    Returns dict with 'tracks' list and 'total' count.
    """
    client = _get_client()
    params = {
        "client_id": config.JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": limit,
        "offset": offset,
        "search": query,
        "include": "musicinfo",
        "audiodlformat": "mp32",  # MP3 VBR ~192kbps
    }

    try:
        resp = await client.get(f"{config.JAMENDO_BASE_URL}/tracks/", params=params)
        resp.raise_for_status()
        data = resp.json()

        tracks = []
        for t in data.get("results", []):
            tracks.append({
                "id": str(t.get("id", "")),
                "title": t.get("name", "Unknown"),
                "artist": t.get("artist_name", "Unknown"),
                "album": t.get("album_name", ""),
                "album_art": t.get("image", ""),
                "stream_url": t.get("audio", ""),
                "duration": int(t.get("duration", 0)),
                "source": "jamendo",
            })

        return {
            "tracks": tracks,
            "total": int(data.get("headers", {}).get("results_fullcount", len(tracks))),
            "source": "jamendo",
        }
    except httpx.HTTPError as e:
        logger.error(f"Jamendo search error: {e}")
        return {"tracks": [], "total": 0, "source": "jamendo"}


async def get_trending(limit: int = 20) -> dict:
    """Get trending/popular tracks from Jamendo."""
    client = _get_client()
    params = {
        "client_id": config.JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": limit,
        "order": "popularity_week",
        "audiodlformat": "mp32",
        "include": "musicinfo",
    }

    try:
        resp = await client.get(f"{config.JAMENDO_BASE_URL}/tracks/", params=params)
        resp.raise_for_status()
        data = resp.json()

        tracks = []
        for t in data.get("results", []):
            tracks.append({
                "id": str(t.get("id", "")),
                "title": t.get("name", "Unknown"),
                "artist": t.get("artist_name", "Unknown"),
                "album": t.get("album_name", ""),
                "album_art": t.get("image", ""),
                "stream_url": t.get("audio", ""),
                "duration": int(t.get("duration", 0)),
                "source": "jamendo",
            })

        return {
            "tracks": tracks,
            "total": len(tracks),
            "source": "jamendo",
        }
    except httpx.HTTPError as e:
        logger.error(f"Jamendo trending error: {e}")
        return {"tracks": [], "total": 0, "source": "jamendo"}


async def get_genres() -> List[str]:
    """Get list of available music genres/tags from Jamendo."""
    # Jamendo uses tags rather than strict genres; return curated list
    return [
        "pop", "rock", "electronic", "hiphop", "jazz", "classical",
        "ambient", "metal", "folk", "indie", "blues", "reggae",
        "soul", "funk", "country", "latin", "soundtrack", "lofi",
        "chillout", "dance", "punk", "rnb", "world", "acoustic",
    ]


async def search_by_genre(genre: str, limit: int = 20) -> dict:
    """Search tracks by genre/tag."""
    client = _get_client()
    params = {
        "client_id": config.JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": limit,
        "tags": genre,
        "order": "popularity_week",
        "audiodlformat": "mp32",
        "include": "musicinfo",
    }

    try:
        resp = await client.get(f"{config.JAMENDO_BASE_URL}/tracks/", params=params)
        resp.raise_for_status()
        data = resp.json()

        tracks = []
        for t in data.get("results", []):
            tracks.append({
                "id": str(t.get("id", "")),
                "title": t.get("name", "Unknown"),
                "artist": t.get("artist_name", "Unknown"),
                "album": t.get("album_name", ""),
                "album_art": t.get("image", ""),
                "stream_url": t.get("audio", ""),
                "duration": int(t.get("duration", 0)),
                "source": "jamendo",
            })

        return {
            "tracks": tracks,
            "total": len(tracks),
            "source": "jamendo",
        }
    except httpx.HTTPError as e:
        logger.error(f"Jamendo genre search error: {e}")
        return {"tracks": [], "total": 0, "source": "jamendo"}


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
