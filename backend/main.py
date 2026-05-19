"""
JamSync — Main FastAPI Application Entry Point.

A real-time synchronized music listening room app.
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .auth import decode_token
from .database import init_db, get_db, async_session
from .models import Room, User
from .routers import auth_routes, music_routes, playlist_routes, room_routes
from .services import jamendo, deezer
from .services.room_manager import room_manager
from . import config

from sqlalchemy import select

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info(f"🎵 Starting {config.APP_NAME} v{config.APP_VERSION}")
    await init_db()
    logger.info("✅ Database initialized")
    yield
    # Shutdown
    await jamendo.close()
    await deezer.close()
    logger.info("👋 Shutting down")


app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description="Free collaborative music listening rooms",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(auth_routes.router)
app.include_router(room_routes.router)
app.include_router(music_routes.router)
app.include_router(playlist_routes.router)


# ── WebSocket Endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    token: str = Query(default=""),
):
    """WebSocket endpoint for real-time room synchronization."""
    # Authenticate via token query param
    payload = decode_token(token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = payload.get("sub")
    username = payload.get("username", "Anonymous")

    # Verify room exists in DB
    async with async_session() as db:
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if room is None:
            await websocket.close(code=4004, reason="Room not found")
            return

        # Get user avatar
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        avatar_url = user.avatar_url if user else ""

    # Accept the WebSocket connection
    await websocket.accept()
    logger.info(f"🔗 {username} connected to room {room_code}")

    # Ensure room exists in manager
    room_manager.get_or_create_room(room_code, room.name if room else room_code, room.creator_id if room else "")

    # Add user to room
    await room_manager.add_user(room_code, user_id, username, websocket, avatar_url)

    try:
        while True:
            # Receive messages from the client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await room_manager.handle_message(room_code, user_id, message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Invalid JSON"},
                })
    except WebSocketDisconnect:
        logger.info(f"🔌 {username} disconnected from room {room_code}")
    except Exception as e:
        logger.error(f"WebSocket error for {username} in {room_code}: {e}")
    finally:
        await room_manager.remove_user(room_code, user_id)


# ── Static Files & SPA Fallback ──────────────────────────────────────────────

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_spa():
    """Serve the main SPA HTML file."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    """SPA fallback — serve index.html for all non-API routes."""
    file_path = STATIC_DIR / full_path
    if file_path.is_file():
        return FileResponse(str(file_path))
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
    }
