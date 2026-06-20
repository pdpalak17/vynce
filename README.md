---
title: Vynce
sdk: docker
app_port: 8000
---

# Vynce - Listen Together, Vibe Together

Vynce is a premium, real-time synchronized music listening room application. Create virtual rooms, invite friends, chat in real-time, and listen to your favorite tracks synchronously - like a virtual collaborative DJ cabin. 

Powered by a sleek FastAPI backend and a responsive, glassmorphic single-page application (SPA) frontend, Vynce brings high-fidelity music streaming from an expansive library of over 80+ Million tracks, smart recommendations, voice search, and personal playlist management directly to your browser.

---

## Features

### 1. Voice-Activated Search
* **Voice Search Integration**: Search for songs hands-free using the built-in microphone button on the search bar.
* **HTML5 Web Speech API**: Leverages browser-native SpeechRecognition (configured for en-IN to capture regional Indian titles and accents accurately).
* **Pulsing Animation Status**: Active recording state displays a glowing, pulsing mic ring.

### 2. Premium YouTube Music-style Overlay Player
* **Glassmorphic Design**: Full-screen sliding overlay featuring a blurry backdrop, premium dark color palette, and micro-animations.
* **Synchronized Progress & Volume**: Fluid range sliders syncing time-elapsed, duration, and volume settings between the small player bar and full screen overlays.
* **Song Actions**: 
  * **Like**: Persists tracks in your Liked Songs library.
  * **Dislike**: Automatically dislikes the track and skips to the next item in the queue.
  * **Add to Playlist**: Drop-up selector to instantly save the track to any of your custom playlists.

### 3. Interactive Player Tabs
* **Up Next**: Displays the upcoming tracks queue. Clicking any song instantly plays it and advances the queue.
* **Lyrics**: Queries JioSaavn's internal lyrics service dynamically to parse and render formatted song lyrics.
* **Related**: Generates 12 curated track recommendations based on the active song's similarity profile.

### 4. Tabbed User Profile & Playlists (CRUD)
* **Playlists Management**: Create, delete, and list custom playlists. Play entire playlists to queue them all at once.
* **Liked Songs**: A dedicated catalog showing all favorited tracks.
* **Listening History**: Tracks and stores every song you play in the database, showing a chronological timeline of your recent streams.

### 5. Neural Network Recommendation Engine (For You Mix)
* **Multi-Layer Perceptron (MLP)**: A neural network built in pure Python (backend/services/recommender.py) dynamically trains user preference vectors.
* **Personalized Scoring**: Evaluates the user's history and likes to score catalog tracks and recommend songs specifically for the user under the For You Mix.
* **Smart Filtering & Exploration**: Excludes disliked tracks and balances exploitation (highly matched songs) with exploration (fresh new content).

### 6. Context-Aware Autoplay
* Automatically finds similar tracks for continuous queue-free play when a song ends.
* **Strict Language & Emotion Alignment**: Candidates are filtered to match the original song's language (e.g., preventing Punjabi/Bihari tracks after a Hindi track) and prioritized by emotion matching (Romantic, Sad, Party) using title semantics.

### 7. Elegant & Premium Redesigned UI
* **Minimalist SVG Icons**: Replaced generic icons on the navigation tabs with responsive, clean SVGs that transition smoothly on hover.
* **Floating Side Navigation**: Implemented floating glassmorphic page-switch arrows pinned to the left and right viewport edges for immersive browsing.
* **Seamless Search Dismissal**: Navigation via arrows automatically closes and clears any active searches, sliding back into the correct subpage view.

### 8. Real-Time WebSocket Rooms
* **Low-Latency Sync**: Seamlessly syncs play, pause, seek, and track-load actions across all room participants.
* **Live Chat Bubble**: Converse with everyone in the room. Shows unique color-coded user avatars.
* **Listener list**: Shows live indicators of users active in the session.

### 9. Network Latency Compensation
* **Dynamic Network Adjustment**: Appends server timestamps to all sync, play, resume, and seek WebSocket events.
* **Latency Calculation**: Frontend calculates transmission delay using network roundtrip difference and compensates the local player's starting positions.

### 10. Global Keyboard Shortcuts
* **Immersive Playback Controls**: Control the application via hotkeys (active only when input/textbox fields are not focused):
  * Space: Toggle Play/Pause.
  * ArrowLeft / ArrowRight: Seek backward/forward 10 seconds.
  * ArrowUp / ArrowDown: Adjust volume levels.
  * N / n: Skip to next track in queue.
  * L / l: Toggle like state for the active song.
  * M / m: Mute or restore volume levels.

### 11. Democratic Queue Voting
* **Collaborative Skip Voting**: Adds Thumbs Up/Down voting controls directly on tracks within a room queue.
* **Skipping Calculation**: If downvotes on a track exceed 50% of active users, the track is automatically skipped and dropped from the queue.

### 12. Offline Caching Service Worker
* **Range-Request Caching**: Service worker (sw.js) intercepts media stream requests to fetch and store files offline in cache storage.
* **Storage Optimization**: Limits cache to the last 20 played audio tracks to save local storage space.
* **Fallback Placeholder**: Displays a premium SVG placeholder image in the minimized player bar when a track's metadata has no album art.

### 13. Secure Email Verification System
* **Verification Code Flow**: Blocks fake email registration by sending a 6-digit verification code to the user's email upon signup or login.
* **SMTP and Log Fallback**: Leverages SMTP for transmission. When outbound traffic on standard ports is blocked by the host platform, codes are output to the server logs for developer accessibility.
* **Integrated Modal Verification**: Seamless verify panels nested directly in the auth sequence that validate the code within a 10-minute expiration window.

---

## Architecture

```
vynce/
├── backend/
│   ├── main.py              # FastAPI app setup, static mounting, and WS server
│   ├── config.py            # Environment configuration
│   ├── database.py          # SQLAlchemy async DB session setup
│   ├── models.py            # SQLite/PostgreSQL SQL models (User, Room, Playlist, LikedSong, UserHistory)
│   ├── schemas.py           # Pydantic schemas for data serialization and verification
│   ├── auth.py              # JWT authentication & password hashing
│   ├── routers/
│   │   ├── auth_routes.py   # User Login/Register/Verify endpoints
│   │   ├── room_routes.py   # Room management CRUD endpoints
│   │   ├── music_routes.py  # Search, lyrics, liked songs, history & curation APIs
│   │   └── playlist_routes.py # Playlist CRUD endpoints
│   ├── services/
│   │   ├── jiosaavn.py      # JioSaavn API client (with TTL cache and web context bypass)
│   │   ├── jamendo.py       # Jamendo API client fallback
│   │   ├── recommender.py   # Neural Network recommender engine (MLP track scoring)
│   │   └── room_manager.py  # WebSocket state sync engine
│   └── static/              # Frontend Single-Page App (SPA)
│       ├── index.html       # HTML layouts, overlays, and modals
│       ├── styles.css       # HSL variables, dark theme, overlays, animations
│       └── app.js           # Core JS SPA router, Speech API, audio, & WS sync
├── .env.example             # Template for configuration
├── LICENSE                  # MIT License File
└── README.md                # System documentation
```

---

## Tech Stack
* **Backend**: FastAPI (Python 3.10+) + WebSockets
* **Database**: Supabase PostgreSQL (Production) / SQLite + aiosqlite (Local development)
* **Auth**: JWT tokens + bcrypt hashing + 6-digit email verification code
* **Music Source**: JioSaavn API + TTL Memory caching decorator
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
Set a secure `JWT_SECRET` value. To use SQLite locally, leave `DATABASE_URL` commented out or empty.

### 4. Run the Dev Server
Launch the FastAPI server using `uvicorn`:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access Vynce
Open http://localhost:8000 in your web browser.

---

## Deployment to Hugging Face Spaces

Vynce is optimized for running on Hugging Face Spaces as a Docker space:

1. Create a new Space on Hugging Face.
2. Select **Docker** as the SDK.
3. Configure the Space environment variables in settings:
   * `DATABASE_URL`: Your Supabase connection string (use session pooler on port 5432).
   * `JWT_SECRET`: A secure random password hashing string.
   * `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`: (Optional) Credentials to send real verification emails.
4. Git push this repository to your Hugging Face Space repository:
   ```bash
   git push hf main
   ```
5. Hugging Face will build the Docker container using the project Dockerfile and launch the space automatically.

---

## License
Vynce is licensed under the MIT License.
