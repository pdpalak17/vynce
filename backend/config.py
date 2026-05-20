"""
Vynce Configuration — Environment variables and app settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Database
_db_url = os.getenv("DATABASE_URL")
if _db_url:
    if _db_url.startswith("postgresql://"):
        DATABASE_URL = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif _db_url.startswith("postgres://"):
        DATABASE_URL = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        DATABASE_URL = _db_url
else:
    DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR / 'vynce.db'}"

# JWT Authentication
JWT_SECRET = os.getenv("JWT_SECRET", "vynce-dev-secret-change-in-production-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "72"))

# Jamendo API
JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID", "")
JAMENDO_BASE_URL = "https://api.jamendo.com/v3.0"

# Deezer API (no key needed for public endpoints)
DEEZER_BASE_URL = "https://api.deezer.com"

# App Settings
APP_NAME = "Vynce"
APP_VERSION = "1.0.0"
MAX_ROOM_SIZE = int(os.getenv("MAX_ROOM_SIZE", "20"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
