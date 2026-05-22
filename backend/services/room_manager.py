"""
Vynce Room Manager — WebSocket-based synchronized music room management.

Handles room state, user connections, playback sync, chat, and queue management.
The server is the authoritative source for playback position.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class RoomUser:
    """A connected user in a room."""
    user_id: str
    username: str
    websocket: WebSocket
    avatar_url: str = ""


@dataclass
class RoomState:
    """Server-side state for a music room."""
    code: str
    name: str
    creator_id: str
    users: Dict[str, RoomUser] = field(default_factory=dict)
    current_track: Optional[dict] = None
    is_playing: bool = False
    playback_position: float = 0.0  # seconds
    playback_started_at: float = 0.0  # time.time() when play started
    queue: List[dict] = field(default_factory=list)
    chat_history: List[dict] = field(default_factory=list)
    history: List[dict] = field(default_factory=list)

    def get_current_position(self) -> float:
        """Calculate current playback position based on server clock."""
        if not self.is_playing or self.current_track is None:
            return self.playback_position
        elapsed = time.time() - self.playback_started_at
        return self.playback_position + elapsed

    def play(self):
        """Resume playback from current position."""
        self.playback_started_at = time.time()
        self.is_playing = True

    def pause(self):
        """Pause playback, saving current position."""
        if self.is_playing:
            self.playback_position = self.get_current_position()
            self.is_playing = False

    def seek(self, position: float):
        """Seek to a specific position."""
        self.playback_position = position
        if self.is_playing:
            self.playback_started_at = time.time()

    def set_track(self, track: dict):
        """Load a new track and reset position."""
        if self.current_track and self.current_track.get("id") != track.get("id"):
            self.history.append(self.current_track)
            if len(self.history) > 50:
                self.history.pop(0)
        self.current_track = track
        self.playback_position = 0.0
        self.playback_started_at = time.time()
        self.is_playing = True


class RoomManager:
    """
    Singleton managing all active music rooms.
    Handles WebSocket connections, broadcasting, and playback sync.
    """

    def __init__(self):
        self.rooms: Dict[str, RoomState] = {}
        self._sync_tasks: Dict[str, asyncio.Task] = {}
        self._filling_rooms = set()

    def get_or_create_room(self, code: str, name: str = "", creator_id: str = "") -> RoomState:
        """Get existing room or create a new one."""
        if code not in self.rooms:
            self.rooms[code] = RoomState(code=code, name=name, creator_id=creator_id)
        return self.rooms[code]

    def get_room(self, code: str) -> Optional[RoomState]:
        """Get room by code, or None."""
        return self.rooms.get(code)

    async def ensure_room_queue_filled(self, room: RoomState):
        """Proactively pre-fill the room's queue if it falls below 5 tracks."""
        if room.code in self._filling_rooms:
            return
        if len(room.queue) >= 5:
            return

        self._filling_rooms.add(room.code)
        try:
            needed = 5 - len(room.queue)
            
            # Determine seed track
            seed_track_id = None
            if room.queue:
                seed_track_id = room.queue[-1].get("id")
            elif room.current_track:
                seed_track_id = room.current_track.get("id")

            tracks_to_add = []
            
            # Try to get similar tracks
            if seed_track_id:
                try:
                    from ..services.jiosaavn import get_similar_tracks
                    res = await get_similar_tracks(seed_track_id, limit=needed + 10)
                    sim_tracks = res.get("tracks", [])
                    
                    existing_ids = {t.get("id") for t in room.queue if t.get("id")}
                    if room.current_track and room.current_track.get("id"):
                        existing_ids.add(room.current_track.get("id"))
                    
                    for t in sim_tracks:
                        tid = t.get("id")
                        if tid and tid not in existing_ids:
                            tracks_to_add.append(t)
                            existing_ids.add(tid)
                            if len(tracks_to_add) >= needed:
                                break
                except Exception as e:
                    logger.error(f"Error fetching similar tracks for room {room.code}: {e}")

            # Fallback: get trending tracks
            if len(tracks_to_add) < needed:
                try:
                    from ..services.jiosaavn import get_trending
                    res = await get_trending(limit=15)
                    trending_tracks = res.get("tracks", [])
                    
                    existing_ids = {t.get("id") for t in room.queue if t.get("id")}
                    if room.current_track and room.current_track.get("id"):
                        existing_ids.add(room.current_track.get("id"))
                    for t in tracks_to_add:
                        if t.get("id"):
                            existing_ids.add(t.get("id"))
                            
                    for t in trending_tracks:
                        tid = t.get("id")
                        if tid and tid not in existing_ids:
                            tracks_to_add.append(t)
                            existing_ids.add(tid)
                            if len(tracks_to_add) >= needed:
                                break
                except Exception as e:
                    logger.error(f"Error fetching trending tracks for room {room.code}: {e}")

            if tracks_to_add:
                room.queue.extend(tracks_to_add)
                await self._broadcast(room, {
                    "type": "queue_update",
                    "data": {"queue": room.queue},
                })
            
            # If there is no current track playing/loaded, set the first one and start playing
            if not room.current_track and room.queue:
                next_track = room.queue.pop(0)
                room.set_track(next_track)
                room.is_playing = True
                await self._broadcast(room, {
                    "type": "play_track",
                    "data": {
                        "track": next_track,
                        "position": 0,
                        "user_id": "system",
                    },
                })
                await self._broadcast(room, {
                    "type": "queue_update",
                    "data": {"queue": room.queue},
                })
        finally:
            self._filling_rooms.discard(room.code)

    async def add_user(self, code: str, user_id: str, username: str, websocket: WebSocket, avatar_url: str = ""):
        """Add a user to a room and notify everyone."""
        room = self.rooms.get(code)
        if room is None:
            return

        room_user = RoomUser(
            user_id=user_id,
            username=username,
            websocket=websocket,
            avatar_url=avatar_url,
        )
        room.users[user_id] = room_user

        # Ensure queue is populated if there is no track playing
        if not room.current_track:
            await self.ensure_room_queue_filled(room)

        # Send current room state to the joining user
        await self._send(websocket, {
            "type": "room_state",
            "data": {
                "room_name": room.name,
                "room_code": room.code,
                "current_track": room.current_track,
                "is_playing": room.is_playing,
                "position": room.get_current_position(),
                "queue": room.queue,
                "users": [
                    {"user_id": u.user_id, "username": u.username, "avatar_url": u.avatar_url}
                    for u in room.users.values()
                ],
                "chat_history": room.chat_history[-50:],  # Last 50 messages
            },
        })

        # Broadcast user joined to everyone else
        await self._broadcast(room, {
            "type": "user_joined",
            "data": {
                "user_id": user_id,
                "username": username,
                "avatar_url": avatar_url,
                "listener_count": len(room.users),
            },
        }, exclude=user_id)

        # Start sync task if not running
        if code not in self._sync_tasks or self._sync_tasks[code].done():
            self._sync_tasks[code] = asyncio.create_task(self._sync_loop(code))

    async def remove_user(self, code: str, user_id: str):
        """Remove a user from a room and notify everyone."""
        room = self.rooms.get(code)
        if room is None:
            return

        user = room.users.pop(user_id, None)
        if user is None:
            return

        # Broadcast user left
        await self._broadcast(room, {
            "type": "user_left",
            "data": {
                "user_id": user_id,
                "username": user.username,
                "listener_count": len(room.users),
            },
        })

        # Clean up empty rooms
        if len(room.users) == 0:
            if code in self._sync_tasks:
                self._sync_tasks[code].cancel()
                del self._sync_tasks[code]
            del self.rooms[code]

    async def handle_message(self, code: str, user_id: str, message: dict):
        """Process an incoming WebSocket message from a user."""
        room = self.rooms.get(code)
        if room is None:
            return

        msg_type = message.get("type", "")
        data = message.get("data", {})

        if msg_type == "play_track":
            # User wants to play a specific track
            track = data.get("track")
            if track:
                room.set_track(track)
                await self._broadcast(room, {
                    "type": "play_track",
                    "data": {
                        "track": track,
                        "position": 0,
                        "user_id": user_id,
                    },
                })
                await self.ensure_room_queue_filled(room)

        elif msg_type == "pause":
            room.pause()
            await self._broadcast(room, {
                "type": "pause",
                "data": {"position": room.playback_position},
            })

        elif msg_type == "resume":
            room.play()
            await self._broadcast(room, {
                "type": "resume",
                "data": {"position": room.playback_position},
            })

        elif msg_type == "seek":
            position = float(data.get("position", 0))
            room.seek(position)
            await self._broadcast(room, {
                "type": "seek",
                "data": {"position": position},
            })

        elif msg_type == "queue_track":
            track = data.get("track")
            if track:
                room.queue.append(track)
                await self._broadcast(room, {
                    "type": "queue_update",
                    "data": {"queue": room.queue},
                })
                await self.ensure_room_queue_filled(room)

        elif msg_type == "skip":
            # Ensure queue is filled first if it's empty
            if not room.queue:
                await self.ensure_room_queue_filled(room)

            # Play next track in queue
            if room.queue:
                next_track = room.queue.pop(0)
                room.set_track(next_track)
                await self._broadcast(room, {
                    "type": "play_track",
                    "data": {
                        "track": next_track,
                        "position": 0,
                        "user_id": user_id,
                    },
                })
                await self._broadcast(room, {
                    "type": "queue_update",
                    "data": {"queue": room.queue},
                })
                await self.ensure_room_queue_filled(room)
            else:
                room.pause()
                room.current_track = None
                await self._broadcast(room, {
                    "type": "track_ended",
                    "data": {},
                })

        elif msg_type == "prev_track":
            # Play previous track in history
            if room.history:
                prev_track = room.history.pop()
                if room.current_track:
                    room.queue.insert(0, room.current_track)
                room.set_track(prev_track)
                await self._broadcast(room, {
                    "type": "play_track",
                    "data": {
                        "track": prev_track,
                        "position": 0,
                        "user_id": user_id,
                    },
                })
                await self._broadcast(room, {
                    "type": "queue_update",
                    "data": {"queue": room.queue},
                })
                await self.ensure_room_queue_filled(room)
            else:
                # Restart current track
                if room.current_track:
                    room.seek(0.0)
                    await self._broadcast(room, {
                        "type": "seek",
                        "data": {"position": 0.0},
                    })

        elif msg_type == "chat_message":
            text = data.get("text", "").strip()
            if text:
                user = room.users.get(user_id)
                chat_msg = {
                    "user_id": user_id,
                    "username": user.username if user else "Unknown",
                    "avatar_url": user.avatar_url if user else "",
                    "text": text,
                    "timestamp": time.time(),
                }
                room.chat_history.append(chat_msg)
                # Keep only last 200 messages
                if len(room.chat_history) > 200:
                    room.chat_history = room.chat_history[-200:]

                await self._broadcast(room, {
                    "type": "chat_message",
                    "data": chat_msg,
                })

        elif msg_type == "remove_from_queue":
            index = data.get("index")
            if index is not None and 0 <= index < len(room.queue):
                room.queue.pop(index)
                await self._broadcast(room, {
                    "type": "queue_update",
                    "data": {"queue": room.queue},
                })
                await self.ensure_room_queue_filled(room)
            else:
                # Restart current track
                if room.current_track:
                    room.seek(0.0)
                    await self._broadcast(room, {
                        "type": "seek",
                        "data": {"position": 0.0},
                    })

        elif msg_type == "chat_message":
            text = data.get("text", "").strip()
            if text:
                user = room.users.get(user_id)
                chat_msg = {
                    "user_id": user_id,
                    "username": user.username if user else "Unknown",
                    "avatar_url": user.avatar_url if user else "",
                    "text": text,
                    "timestamp": time.time(),
                }
                room.chat_history.append(chat_msg)
                # Keep only last 200 messages
                if len(room.chat_history) > 200:
                    room.chat_history = room.chat_history[-200:]

                await self._broadcast(room, {
                    "type": "chat_message",
                    "data": chat_msg,
                })

        elif msg_type == "remove_from_queue":
            index = data.get("index")
            if index is not None and 0 <= index < len(room.queue):
                room.queue.pop(index)
                await self._broadcast(room, {
                    "type": "queue_update",
                    "data": {"queue": room.queue},
                })

    async def _sync_loop(self, code: str):
        """Periodically broadcast playback sync to all clients in a room."""
        try:
            while code in self.rooms:
                room = self.rooms[code]
                
                # Proactively ensure the queue is filled if it drops below 5
                if len(room.queue) < 5:
                    await self.ensure_room_queue_filled(room)

                if room.is_playing and room.current_track:
                    position = room.get_current_position()
                    duration = room.current_track.get("duration", 0)

                    # Auto-advance to next track when current ends
                    if duration > 0 and position >= duration:
                        if room.queue:
                            next_track = room.queue.pop(0)
                            room.set_track(next_track)
                            await self._broadcast(room, {
                                "type": "play_track",
                                "data": {
                                    "track": next_track,
                                    "position": 0,
                                    "user_id": "system",
                                },
                            })
                            await self._broadcast(room, {
                                "type": "queue_update",
                                "data": {"queue": room.queue},
                            })
                            await self.ensure_room_queue_filled(room)
                        else:
                            # Autoplay next similar song fallback
                            try:
                                from ..services.jiosaavn import get_similar_tracks
                                current_id = room.current_track.get("id")
                                if current_id:
                                    logger.info(f"Room {code} queue empty, autoplaying similar song for track {current_id}")
                                    sim_res = await get_similar_tracks(current_id, limit=5)
                                    sim_tracks = sim_res.get("tracks", [])
                                    if sim_tracks:
                                        next_track = sim_tracks[0]
                                        room.set_track(next_track)
                                        await self._broadcast(room, {
                                            "type": "play_track",
                                            "data": {
                                                "track": next_track,
                                                "position": 0,
                                                "user_id": "system",
                                            },
                                        })
                                        await self.ensure_room_queue_filled(room)
                                        continue
                            except Exception as ex:
                                logger.error(f"Autoplay similar song error in room {code}: {ex}")

                            room.pause()
                            room.current_track = None
                            await self._broadcast(room, {
                                "type": "track_ended",
                                "data": {},
                            })
                    else:
                        # Send sync pulse
                        await self._broadcast(room, {
                            "type": "sync",
                            "data": {
                                "position": position,
                                "is_playing": room.is_playing,
                                "server_time": time.time(),
                            },
                        })

                await asyncio.sleep(2)  # Sync every 2 seconds
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Sync loop error for room {code}: {e}")

    async def _broadcast(self, room: RoomState, message: dict, exclude: str = None):
        """Send a message to all users in a room, optionally excluding one."""
        disconnected = []
        for uid, user in room.users.items():
            if uid == exclude:
                continue
            try:
                await self._send(user.websocket, message)
            except Exception:
                disconnected.append(uid)

        # Clean up disconnected users
        for uid in disconnected:
            room.users.pop(uid, None)

    async def _send(self, ws: WebSocket, message: dict):
        """Send a JSON message through a WebSocket."""
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.debug(f"WebSocket send error: {e}")
            raise

    def get_room_info(self, code: str) -> Optional[dict]:
        """Get public info about a room (for API responses)."""
        room = self.rooms.get(code)
        if room is None:
            return None
        return {
            "code": room.code,
            "name": room.name,
            "listener_count": len(room.users),
            "current_track": room.current_track,
            "is_playing": room.is_playing,
        }


# Global singleton
room_manager = RoomManager()
