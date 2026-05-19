"""
JamSync Models — SQLAlchemy ORM models for User, Room, Playlist, RoomHistory.
"""

import datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


def generate_uuid():
    return str(uuid.uuid4())


def generate_room_code():
    return uuid.uuid4().hex[:6].upper()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    avatar_url = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    rooms = relationship("Room", back_populates="creator", lazy="selectin")
    playlists = relationship("Playlist", back_populates="owner", lazy="selectin")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    code = Column(String(6), unique=True, nullable=False, default=generate_room_code, index=True)
    creator_id = Column(String, ForeignKey("users.id"), nullable=False)
    is_public = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    creator = relationship("User", back_populates="rooms", lazy="selectin")
    history = relationship("RoomHistory", back_populates="room", lazy="selectin")


class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    tracks = Column(Text, default="[]")  # JSON string of track objects
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="playlists", lazy="selectin")


class RoomHistory(Base):
    __tablename__ = "room_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(String, ForeignKey("rooms.id"), nullable=False)
    track_title = Column(String(200))
    track_artist = Column(String(200))
    track_source = Column(String(50))
    played_at = Column(DateTime, default=datetime.datetime.utcnow)

    room = relationship("Room", back_populates="history", lazy="selectin")
