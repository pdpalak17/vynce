# Vynce — Listen Together, Vibe Together

Vynce is a premium, real-time synchronized music listening room application. Create virtual rooms, invite friends, chat in real-time, and listen to your favorite tracks synchronously — like a virtual collaborative DJ cabin. 

Powered by a sleek FastAPI backend and a responsive, glassmorphic single-page application (SPA) frontend, Vynce brings high-fidelity music streaming from an expansive library of **over 80+ Million tracks**, smart recommendations, voice search, and personal playlist management directly to your browser.

![Vynce](https://img.shields.io/badge/Vynce-v2.0.0-00E5FF?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-00D4FF?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-00FF88?style=for-the-badge&logo=fastapi&logoColor=white)
![WebSockets](https://img.shields.io/badge/WebSockets-Real--Time-FF007F?style=for-the-badge&logo=socket.io&logoColor=white)

---

## Features

### 🎙️ 1. Voice-Activated Search
* **Voice Search Integration**: Search for songs hands-free using the built-in microphone button on the search bar.
* **HTML5 Web Speech API**: Leverages browser-native `SpeechRecognition` (configured for `en-IN` to capture regional Indian titles and accents accurately).
* **Pulsing Animation Status**: Active recording state displays a glowing, pulsing mic ring.

### 🎧 2. Premium YouTube Music-style Overlay Player
* **Glassmorphism Design**: Full-screen sliding overlay featuring a blurry backdrop, premium dark color palette, and micro-animations.
* **Synchronized Progress & Volume**: Fluid range sliders syncing time-elapsed, duration, and volume settings between the small player bar and full screen overlays.
* **Song Actions**: 
  * **Like**: Persists tracks in your Liked Songs library.
  * **Dislike**: Automatically dislikes the track and skips to the next item in the queue.
  * **Add to Playlist**: Drop-up selector to instantly save the track to any of your custom playlists.

### 📑 3. Interactive Player Tabs
* **Up Next**: Displays the upcoming tracks queue. Clicking any song instantly plays it and advances the queue.
* **Lyrics**: Queries JioSaavn's internal lyrics service dynamically to parse and render formatted song lyrics.
* **Related**: Generates 12 curated track recommendations based on the active song's similarity profile.

### 📂 4. Tabbed User Profile & Playlists (CRUD)
* **Playlists Management**: Create, delete, and list custom playlists. Play entire playlists to queue them all at once.
* **Liked Songs**: A dedicated catalog showing all favorited tracks.
* **Listening History**: Tracks and stores every song you play in an SQLite database, showing a chronological timeline of your recent streams just like Spotify.

### 🧠 5. Neural Network Recommendation Engine (For You Mix)
* **Multi-Layer Perceptron (MLP)**: A neural network built in pure Python (`backend/services/recommender.py`) dynamically trains user preference vectors.
* **Personalized Scoring**: Evaluates the user's history and likes to score catalog tracks and recommend songs specifically for the user under the **For You Mix**.
* **Smart Filtering & Exploration**: Excludes disliked tracks and balances exploitation (highly matched songs) with exploration (fresh new content).

### 📻 6. Context-Aware Autoplay
* Automatically finds similar tracks for continuous queue-free play when a song ends.
* **Strict Language & Emotion Alignment**: Candidates are filtered to match the original song's language (e.g., preventing Punjabi/Bihari tracks after a Hindi track) and prioritized by emotion matching (Romantic, Sad, Party) using title semantics.

### 🎨 7. Elegant & Premium Redesigned UI
* **Minimalist SVG Icons**: Replaced childish emojis on the navigation tabs with responsive, clean SVGs that transition smoothly on hover.
* **Floating Side Navigation**: Implemented floating glassmorphic page-switch arrows pinned to the left and right viewport edges for immersive browsing.
* **Seamless Search Dismissal**: Navigation via arrows automatically closes and cleanses any active searches, sliding back into the correct subpage view.

### 👥 8. Real-Time WebSocket Rooms
* **Low-Latency Sync**: Seamlessly syncs play, pause, seek, and track-load actions across all room participants.
* **Live Chat Bubble**: Converse with everyone in the room. Shows unique color-coded user avatars.
* **Listener list**: Shows live indicators of users active in the session.

---

## Architecture

```
vynce/
├── backend/
│   ├── main.py              # FastAPI app setup, static mounting, and WS server
│   ├── config.py            # Environment configuration
│   ├── database.py          # SQLAlchemy async DB session setup
│   ├── models.py            # SQLite SQL models (User, Room, Playlist, LikedSong, UserHistory)
│   ├── schemas.py           # Pydantic schemas for data serialization and verification
│   ├── auth.py              # JWT authentication & password hashing
│   ├── routers/
│   │   ├── auth_routes.py   # User Login/Register endpoints
│   │   ├── room_routes.py   # Room management CRUD endpoints
│   │   ├── music_routes.py  # Search, lyrics, liked songs, history & curation APIs
│   │   └── playlist_routes.py # Playlist CRUD endpoints
│   ├── services/
│   │   ├── jiosaavn.py      # JioSaavn API client (with proxy bypass header injection)
│   │   ├── jamendo.py       # Jamendo API client fallback
│   │   ├── recommender.py   # Neural Network recommender engine (MLP track scoring)
│   │   └── room_manager.py  # WebSocket state sync engine
│   └── static/              # Frontend Single-Page App (SPA)
│       ├── index.html       # HTML layouts, overlays, and modals
│       ├── styles.css       # HSL variables, dark theme, overlays, animations
│       └── app.js           # Core JS SPA router, Speech API, audio, & WS sync
├── .env.example             # Template for configuration
├── LICENSE                  # MIT License File
├── render.yaml              # Render.com deployment setup
├── Procfile                 # Production WSGI process file
└── README.md                # System documentation
```

---

## Tech Stack
* **Backend**: FastAPI (Python) + WebSockets
* **Database**: SQLite + SQLAlchemy (Async engine)
* **Auth**: JWT tokens + bcrypt hashing
* **Music Source**: JioSaavn API (with fallback support) + geo-restriction bypass proxy headers
* **Frontend**: Vanilla HTML5 / CSS3 / JavaScript (ES6)
* **Design Guidelines**: Glassmorphism, CSS animations, HSL variables

---

## Local Setup Guide

### 1. Prerequisites
* Python 3.10+ installed on your computer.

### 2. Clone and Install Dependencies
Navigate to your project directory and install backend requirements:
```bash
pip install -r backend/requirements.txt
```

### 3. Setup Environment Variables
Create a `.env` file in the root directory by copying the example:
```bash
cp .env.example .env
```
Ensure you set a secure `JWT_SECRET` value.

### 4. Run the Dev Server
Launch the FastAPI server using `uvicorn`:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access Vynce
Open [http://localhost:8000](http://localhost:8000) in your web browser. 🎉

---

## Deployment to Render.com
1. Commit and push the code to your GitHub repository.
2. Sign in to [Render.com](https://render.com) and create a **New Web Service**.
3. Link your GitHub repository.
4. Set the following Environment Variables:
   * `JWT_SECRET`: A secure random password hashing string.
5. Render will automatically read `render.yaml` or you can deploy with:
   * **Build Command**: `pip install -r backend/requirements.txt`
   * **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
6. Deploy! 🚀

---

## 📄 License
Vynce is licensed under the [MIT License](file:///C:/Users/palak/.gemini/antigravity/scratch/vynce/LICENSE). 

*Note: Streamed music is powered by external public catalogs. Please check the licensing guidelines of individual music providers for commercial usage.*
