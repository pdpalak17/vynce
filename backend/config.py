"""
Vynce Configuration - Environment variables and app settings.
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
if not _db_url:
    # Fallback to local SQLite if environment variable is missing so Vercel doesn't crash on boot
    DATABASE_URL = "sqlite+aiosqlite:///backend/vynce.db"
    print("WARNING: DATABASE_URL not found. Falling back to SQLite.")
elif _db_url.startswith("postgresql://"):
    DATABASE_URL = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _db_url.startswith("postgres://"):
    DATABASE_URL = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _db_url

# JWT Authentication
JWT_SECRET = os.getenv("JWT_SECRET", "vynce-dev-secret-change-in-production-2026")
JWT_ALGORITHM = "HS256"
_jwt_expiry = os.getenv("JWT_EXPIRY_HOURS", "72")
JWT_EXPIRY_HOURS = int(_jwt_expiry) if _jwt_expiry else 72

# Jamendo API
JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID", "")
JAMENDO_BASE_URL = "https://api.jamendo.com/v3.0"

# Deezer API (no key needed for public endpoints)
DEEZER_BASE_URL = "https://api.deezer.com"

# App Settings
APP_NAME = "Vynce"
APP_VERSION = "1.0.0"
_max_room_size = os.getenv("MAX_ROOM_SIZE", "20")
MAX_ROOM_SIZE = int(_max_room_size) if _max_room_size else 20
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
_port = os.getenv("PORT", "8000")
PORT = int(_port) if _port else 8000

# AbstractAPI Email Validation
EMAIL_VERIFICATION_API_KEY = os.getenv("EMAIL_VERIFICATION_API_KEY", "")
