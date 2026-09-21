import json
import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import RoomLiveState
from ..services.jiosaavn import get_similar_tracks, get_trending

logger = logging.getLogger(__name__)

async def _get_db_state(db: AsyncSession, room_code: str) -> RoomLiveState:
    result = await db.execute(select(RoomLiveState).where(RoomLiveState.room_code == room_code))
    state = result.scalar_one_or_none()
    if not state:
        state = RoomLiveState(room_code=room_code)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state

def _calculate_position(state: RoomLiveState, current_track: dict) -> float:
    position = state.playback_position
    if state.is_playing and current_track:
        elapsed = time.time() - state.playback_started_at
        position += elapsed
    return position

async def get_or_create_room_state(db: AsyncSession, room_code: str) -> dict:
    state = await _get_db_state(db, room_code)
    
    current_track = json.loads(state.current_track) if state.current_track else None
    queue = json.loads(state.queue)
    chat_history = json.loads(state.chat_history)
    history = json.loads(state.history)
    removed_track_ids = json.loads(state.removed_track_ids)
    
    position = _calculate_position(state, current_track)
    
    if state.is_playing and current_track:
        duration = current_track.get("duration", 0)
        if duration > 0 and position >= duration:
            if queue:
                next_track = queue.pop(0)
                state.current_track = json.dumps(next_track)
                state.queue = json.dumps(queue)
                state.playback_position = 0.0
                state.playback_started_at = time.time()
                state.is_playing = True
                
                history.append(current_track)
                if len(history) > 50:
                    history.pop(0)
                state.history = json.dumps(history)
                
                current_track = next_track
                position = 0.0
                await db.commit()
            else:
                state.is_playing = False
                state.playback_position = duration
                await db.commit()

    if len(queue) < 5:
        await _ensure_queue_filled(db, state, queue, current_track, history, removed_track_ids)

    return {
        "room_code": state.room_code,
        "current_track": current_track,
        "is_playing": state.is_playing,
        "position": position,
        "queue": queue,
        "chat_history": chat_history[-50:],
        "server_time": time.time()
    }

async def _ensure_queue_filled(db: AsyncSession, state: RoomLiveState, queue: list, current_track: dict, history: list, removed_track_ids: list):
    needed = 5 - len(queue)
    seed_track_id = queue[-1].get("id") if queue else (current_track.get("id") if current_track else None)
    
    tracks_to_add = []
    existing_ids = {t.get("id") for t in queue if t.get("id")}
    if current_track and current_track.get("id"):
        existing_ids.add(current_track.get("id"))
    for h in history:
        if h and h.get("id"):
            existing_ids.add(h.get("id"))
    existing_ids.update(removed_track_ids)

    if seed_track_id:
        try:
            res = await get_similar_tracks(seed_track_id, limit=needed + 10)
            sim_tracks = res.get("tracks", [])
            for t in sim_tracks:
                tid = t.get("id")
                if tid and tid not in existing_ids:
                    tracks_to_add.append(t)
                    existing_ids.add(tid)
                    if len(tracks_to_add) >= needed:
                        break
        except Exception as e:
            logger.error(f"Error fetching similar tracks: {e}")

    if len(tracks_to_add) < needed:
        try:
            res = await get_trending(limit=15)
            trending_tracks = res.get("tracks", [])
            for t in trending_tracks:
                tid = t.get("id")
                if tid and tid not in existing_ids:
                    tracks_to_add.append(t)
                    existing_ids.add(tid)
                    if len(tracks_to_add) >= needed:
                        break
        except Exception as e:
            logger.error(f"Error fetching trending tracks: {e}")

    if tracks_to_add:
        queue.extend(tracks_to_add)
        state.queue = json.dumps(queue)
        if not current_track and queue:
            next_track = queue.pop(0)
            state.current_track = json.dumps(next_track)
            state.queue = json.dumps(queue)
            state.playback_position = 0.0
            state.playback_started_at = time.time()
            state.is_playing = True
        await db.commit()

async def play_track_action(db: AsyncSession, room_code: str, track: dict):
    state = await _get_db_state(db, room_code)
    tid = track.get("id")
    removed = json.loads(state.removed_track_ids)
    if tid and tid in removed:
        removed.remove(tid)
        state.removed_track_ids = json.dumps(removed)
    
    current_track = json.loads(state.current_track) if state.current_track else None
    history = json.loads(state.history)
    if current_track and current_track.get("id") != track.get("id"):
        history.append(current_track)
        if len(history) > 50:
            history.pop(0)
        state.history = json.dumps(history)
        
    state.current_track = json.dumps(track)
    state.playback_position = 0.0
    state.playback_started_at = time.time()
    state.is_playing = True
    await db.commit()

async def pause_action(db: AsyncSession, room_code: str):
    state = await _get_db_state(db, room_code)
    if state.is_playing:
        current_track = json.loads(state.current_track) if state.current_track else None
        state.playback_position = _calculate_position(state, current_track)
        state.is_playing = False
        await db.commit()

async def resume_action(db: AsyncSession, room_code: str):
    state = await _get_db_state(db, room_code)
    if not state.is_playing:
        state.playback_started_at = time.time()
        state.is_playing = True
        await db.commit()

async def seek_action(db: AsyncSession, room_code: str, position: float):
    state = await _get_db_state(db, room_code)
    state.playback_position = position
    if state.is_playing:
        state.playback_started_at = time.time()
    await db.commit()

async def queue_track_action(db: AsyncSession, room_code: str, track: dict):
    state = await _get_db_state(db, room_code)
    queue = json.loads(state.queue)
    queue.append(track)
    state.queue = json.dumps(queue)
    tid = track.get("id")
    removed = json.loads(state.removed_track_ids)
    if tid and tid in removed:
        removed.remove(tid)
        state.removed_track_ids = json.dumps(removed)
    
    current_track = json.loads(state.current_track) if state.current_track else None
    if not current_track:
        next_track = queue.pop(0)
        state.current_track = json.dumps(next_track)
        state.queue = json.dumps(queue)
        state.playback_position = 0.0
        state.playback_started_at = time.time()
        state.is_playing = True
        
    await db.commit()

async def skip_action(db: AsyncSession, room_code: str):
    state = await _get_db_state(db, room_code)
    queue = json.loads(state.queue)
    current_track = json.loads(state.current_track) if state.current_track else None
    history = json.loads(state.history)
    
    if current_track:
        history.append(current_track)
        if len(history) > 50:
            history.pop(0)
        state.history = json.dumps(history)
        
    if queue:
        next_track = queue.pop(0)
        state.current_track = json.dumps(next_track)
        state.queue = json.dumps(queue)
        state.playback_position = 0.0
        state.playback_started_at = time.time()
        state.is_playing = True
    else:
        state.current_track = None
        state.is_playing = False
        state.playback_position = 0.0
    await db.commit()

async def prev_action(db: AsyncSession, room_code: str):
    state = await _get_db_state(db, room_code)
    history = json.loads(state.history)
    queue = json.loads(state.queue)
    current_track = json.loads(state.current_track) if state.current_track else None
    
    if history:
        prev_track = history.pop()
        if current_track:
            queue.insert(0, current_track)
            state.queue = json.dumps(queue)
        state.current_track = json.dumps(prev_track)
        state.history = json.dumps(history)
        state.playback_position = 0.0
        state.playback_started_at = time.time()
        state.is_playing = True
    else:
        if current_track:
            state.playback_position = 0.0
            state.playback_started_at = time.time()
    await db.commit()

async def chat_message_action(db: AsyncSession, room_code: str, user_id: str, username: str, avatar_url: str, text: str):
    state = await _get_db_state(db, room_code)
    chat_history = json.loads(state.chat_history)
    msg = {
        "user_id": user_id,
        "username": username,
        "avatar_url": avatar_url,
        "text": text,
        "timestamp": time.time()
    }
    chat_history.append(msg)
    if len(chat_history) > 200:
        chat_history = chat_history[-200:]
    state.chat_history = json.dumps(chat_history)
    await db.commit()

async def remove_queue_action(db: AsyncSession, room_code: str, index: int):
    state = await _get_db_state(db, room_code)
    queue = json.loads(state.queue)
    if 0 <= index < len(queue):
        removed = queue.pop(index)
        state.queue = json.dumps(queue)
        removed_ids = json.loads(state.removed_track_ids)
        if removed and removed.get("id"):
            removed_ids.append(removed.get("id"))
            state.removed_track_ids = json.dumps(removed_ids)
        await db.commit()
