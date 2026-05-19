"""
JamSync Deezer Service — Async client for the Deezer public API.
Provides 30-second previews for mainstream music discovery.
"""

import logging
from typing import Optional

import httpx

from .. import config

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15.0)
    return _client


async def search_tracks(query: str, limit: int = 20) -> dict:
    """
    Search Deezer for tracks. Returns 30-second preview URLs.
    No API key required for public endpoints.
    """
    client = _get_client()

    try:
        resp = await client.get(
            f"{config.DEEZER_BASE_URL}/search",
            params={"q": query, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()

        tracks = []
        for t in data.get("data", []):
            preview = t.get("preview", "")
            if not preview:
                continue
            tracks.append({
                "id": f"dz-{t.get('id', '')}",
                "title": t.get("title", "Unknown"),
                "artist": t.get("artist", {}).get("name", "Unknown"),
                "album": t.get("album", {}).get("title", ""),
                "album_art": t.get("album", {}).get("cover_big", t.get("album", {}).get("cover_medium", "")),
                "stream_url": preview,
                "duration": int(t.get("duration", 30)),
                "source": "deezer",
            })

        return {
            "tracks": tracks,
            "total": int(data.get("total", len(tracks))),
            "source": "deezer",
        }
    except httpx.HTTPError as e:
        logger.error(f"Deezer search error: {e}")
        return {"tracks": [], "total": 0, "source": "deezer"}


async def get_trending(limit: int = 20) -> dict:
    """Get trending tracks from Deezer charts."""
    client = _get_client()

    try:
        resp = await client.get(
            f"{config.DEEZER_BASE_URL}/chart/0/tracks",
            params={"limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()

        tracks = []
        for t in data.get("data", []):
            preview = t.get("preview", "")
            if not preview:
                continue
            tracks.append({
                "id": f"dz-{t.get('id', '')}",
                "title": t.get("title", "Unknown"),
                "artist": t.get("artist", {}).get("name", "Unknown"),
                "album": t.get("album", {}).get("title", ""),
                "album_art": t.get("album", {}).get("cover_big", t.get("album", {}).get("cover_medium", "")),
                "stream_url": preview,
                "duration": int(t.get("duration", 30)),
                "source": "deezer",
            })

        return {
            "tracks": tracks,
            "total": len(tracks),
            "source": "deezer",
        }
    except httpx.HTTPError as e:
        logger.error(f"Deezer trending error: {e}")
        return {"tracks": [], "total": 0, "source": "deezer"}


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
