"""
Vynce Room State Routes - HTTP polling for room sync (Serverless/Vercel).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..auth import get_current_user
from ..models import User
from ..services import room_state as rs

router = APIRouter(prefix="/api/rooms/{code}", tags=["room_state"])

class TrackPayload(BaseModel):
    track: dict

class SeekPayload(BaseModel):
    position: float

class IndexPayload(BaseModel):
    index: int

class ChatPayload(BaseModel):
    text: str

@router.get("/state")
async def get_state(code: str, db: AsyncSession = Depends(get_db)):
    return await rs.get_or_create_room_state(db, code.upper())

@router.post("/play")
async def play_track(code: str, payload: TrackPayload, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.play_track_action(db, code.upper(), payload.track)
    return {"status": "ok"}

@router.post("/pause")
async def pause_track(code: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.pause_action(db, code.upper())
    return {"status": "ok"}

@router.post("/resume")
async def resume_track(code: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.resume_action(db, code.upper())
    return {"status": "ok"}

@router.post("/seek")
async def seek_track(code: str, payload: SeekPayload, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.seek_action(db, code.upper(), payload.position)
    return {"status": "ok"}

@router.post("/queue")
async def queue_track(code: str, payload: TrackPayload, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.queue_track_action(db, code.upper(), payload.track)
    return {"status": "ok"}

@router.post("/skip")
async def skip_track(code: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.skip_action(db, code.upper())
    return {"status": "ok"}

@router.post("/prev")
async def prev_track(code: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.prev_action(db, code.upper())
    return {"status": "ok"}

@router.post("/remove-queue")
async def remove_queue(code: str, payload: IndexPayload, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.remove_queue_action(db, code.upper(), payload.index)
    return {"status": "ok"}

@router.post("/chat")
async def send_chat(code: str, payload: ChatPayload, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await rs.chat_message_action(db, code.upper(), user.id, user.username, user.avatar_url, payload.text)
    return {"status": "ok"}
