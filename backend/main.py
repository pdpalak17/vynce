"""
Vynce - Main FastAPI Application Entry Point.

A real-time synchronized music listening room app.
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .auth import decode_token
from .database import init_db, get_db, async_session
from .models import Room, User
from .routers import auth_routes, music_routes, playlist_routes, room_routes, room_state_routes
from .services import jamendo, deezer
from . import config

from sqlalchemy import select

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
app.add_middleware(GZipMiddleware, minimum_size=1000)

# API Routers
app.include_router(auth_routes.router)
app.include_router(room_routes.router)
app.include_router(room_state_routes.router)
app.include_router(music_routes.router)
app.include_router(playlist_routes.router)


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
    }
