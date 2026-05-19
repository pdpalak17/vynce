# 🎵 JamSync — Listen Together, Vibe Together

A free, real-time synchronized music listening room app. Create rooms, invite friends, and listen to the same song at the same time — like a virtual DJ room.

![JamSync](https://img.shields.io/badge/JamSync-v1.0.0-7B2FFF?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-00D4FF?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-00FF88?style=for-the-badge&logo=fastapi&logoColor=white)

## ✨ Features

- 🎧 **Synchronized Playback** — Everyone in a room hears the same song at the same time
- 💬 **Live Chat** — Chat with other listeners in real-time
- 🔍 **Music Search** — Search 600k+ free tracks from Jamendo + Deezer previews
- 📋 **Playlists** — Create and manage personal playlists
- 🎛️ **Queue System** — Queue up songs for continuous listening
- 👥 **Room Management** — Create public/private rooms with invite codes
- 🔒 **User Accounts** — Register, login, and manage your profile
- 🆓 **100% Free** — No subscriptions, no ads, powered by Creative Commons music

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- A free [Jamendo API Client ID](https://developer.jamendo.com)

### 1. Clone & Install

```bash
cd jamsync
pip install -r backend/requirements.txt
```

### 2. Configure

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your Jamendo Client ID
# Get one free at: https://developer.jamendo.com
```

### 3. Run

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Open

Navigate to [http://localhost:8000](http://localhost:8000) 🎉

## 🏗️ Architecture

```
jamsync/
├── backend/
│   ├── main.py              # FastAPI app + WebSocket endpoint
│   ├── config.py            # Environment configuration
│   ├── database.py          # SQLAlchemy async setup
│   ├── models.py            # DB models (User, Room, Playlist)
│   ├── schemas.py           # Pydantic validation schemas
│   ├── auth.py              # JWT authentication
│   ├── routers/
│   │   ├── auth_routes.py   # Login/Register
│   │   ├── room_routes.py   # Room CRUD
│   │   ├── music_routes.py  # Music search/trending
│   │   └── playlist_routes.py
│   ├── services/
│   │   ├── jamendo.py       # Jamendo API client
│   │   ├── deezer.py        # Deezer API client
│   │   └── room_manager.py  # WebSocket room sync
│   └── static/              # Frontend SPA
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── .env.example
├── render.yaml              # Render.com deployment
├── Procfile                 # Alternative deployment
└── README.md
```

## 🎵 Music Sources

| Source | Type | Catalog |
|--------|------|---------|
| **Jamendo** | Full-length CC tracks | 600,000+ tracks |
| **Deezer** | 30-second previews | Millions of tracks |

## 🌐 Deploy to Render (Free)

1. Push code to a GitHub repo
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your repo
4. Set environment variables:
   - `JWT_SECRET` → Generate a random secret
   - `JAMENDO_CLIENT_ID` → Your Jamendo key
5. Deploy! 🚀

## 🔧 Tech Stack

- **Backend**: FastAPI (Python) + WebSockets
- **Database**: SQLite + SQLAlchemy (async)
- **Auth**: JWT + bcrypt
- **Music**: Jamendo API + Deezer API
- **Frontend**: Vanilla HTML/CSS/JS
- **Design**: Glassmorphism + Neon accents

## 📄 License

MIT License. Music provided via Jamendo is under Creative Commons licenses.
