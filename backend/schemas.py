"""
Vynce Schemas — Pydantic models for request/response validation.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ── Auth Schemas ──────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    avatar_url: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class RegisterResponse(BaseModel):
    requires_verification: bool = True
    email: str
    message: str
    code: Optional[str] = None


class UserVerify(BaseModel):
    email: str
    code: str


# ── Room Schemas ──────────────────────────────────────────────────────────────

class RoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_public: bool = True


class RoomResponse(BaseModel):
    id: str
    name: str
    code: str
    creator_id: str
    is_public: bool
    is_active: bool
    created_at: datetime
    creator_username: Optional[str] = None
    listener_count: int = 0
    current_track: Optional[dict] = None

    class Config:
        from_attributes = True


# ── Track Schemas ─────────────────────────────────────────────────────────────

class TrackInfo(BaseModel):
    id: str
    title: str
    artist: str
    album: str = ""
    album_art: str = ""
    stream_url: str = ""
    duration: int = 0  # seconds
    source: str = "jamendo"  # "jamendo" or "deezer"


class SearchResponse(BaseModel):
    tracks: List[TrackInfo]
    total: int = 0
    source: str = "jamendo"


# ── Playlist Schemas ──────────────────────────────────────────────────────────

class PlaylistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None
    tracks: Optional[List[dict]] = None


class PlaylistResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    tracks: str  # JSON string
    created_at: datetime

    class Config:
        from_attributes = True


# ── WebSocket Message Schemas ─────────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str
    data: Optional[dict] = None


# ── Liked & History Schemas ───────────────────────────────────────────────────

class LikedSongCreate(BaseModel):
    track_id: str
    track_title: str
    track_artist: str
    track_album: Optional[str] = ""
    track_album_art: Optional[str] = ""
    track_stream_url: Optional[str] = ""


class LikedSongResponse(BaseModel):
    id: int
    user_id: str
    track_id: str
    track_title: str
    track_artist: str
    track_album: Optional[str] = ""
    track_album_art: Optional[str] = ""
    track_stream_url: Optional[str] = ""
    liked_at: datetime

    class Config:
        from_attributes = True


class UserHistoryCreate(BaseModel):
    track_id: str
    track_title: str
    track_artist: str
    track_album: Optional[str] = ""
    track_album_art: Optional[str] = ""
    track_stream_url: Optional[str] = ""


class UserHistoryResponse(BaseModel):
    id: int
    user_id: str
    track_id: str
    track_title: str
    track_artist: str
    track_album: Optional[str] = ""
    track_album_art: Optional[str] = ""
    track_stream_url: Optional[str] = ""
    played_at: datetime

    class Config:
        from_attributes = True


class HomeSectionResponse(BaseModel):
    title: str
    tracks: List[dict]

