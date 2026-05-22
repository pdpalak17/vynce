/* ═══════════════════════════════════════════════════════════════
   Vynce v2 — Main SPA Logic
   Search · Play · Rooms · WebSocket Sync · Chat
   ═══════════════════════════════════════════════════════════════ */
'use strict';

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const escapeHtml = s => { const m = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}; return String(s).replace(/[&<>"']/g,c=>m[c]); };
const formatTime = s => { if(!s||!isFinite(s)) return '0:00'; return `${Math.floor(s/60)}:${Math.floor(s%60).toString().padStart(2,'0')}`; };
const debounce = (fn,ms) => { let t; return (...a) => { clearTimeout(t); t=setTimeout(()=>fn(...a),ms); }; };
const nameColor = n => `hsl(${[...n].reduce((h,c)=>c.charCodeAt(0)+((h<<5)-h),0)%360},65%,55%)`;

/* ═══════ STATE ═══════ */
const state = {
  user: null, token: null, currentRoom: null, currentTrack: null,
  isPlaying: false, volume: 0.7, queue: [], history: [], rooms: [], ws: null,
  likedSongs: new Set(),
};

/* ═══════ AUDIO & HIGH-FIDELITY PROCESSING ═══════ */
const audio = new Audio();
audio.crossOrigin = 'anonymous';
audio.preload = 'auto';
const savedVol = localStorage.getItem('vynce_volume');
if (savedVol !== null) state.volume = parseFloat(savedVol);
audio.volume = state.volume;

// Web Audio API Pipeline for Hi-Fi Enhancement
let audioCtx = null;
let sourceNode = null;
let filterBass = null;
let filterMid = null;
let filterTreble = null;
let compressor = null;
let isAudioPipelineInitialized = false;

function initAudioPipeline() {
  if (isAudioPipelineInitialized) return;
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    audioCtx = new AudioContextClass();

    // Create MediaElementSource from the audio tag
    sourceNode = audioCtx.createMediaElementSource(audio);

    // Bass Filter (warmth & sub-bass boost around 80Hz)
    filterBass = audioCtx.createBiquadFilter();
    filterBass.type = 'peaking';
    filterBass.frequency.value = 80;
    filterBass.Q.value = 1.0;
    filterBass.gain.value = 4.0; // Default warm boost

    // Mid range Filter (voice clarity & presence around 1kHz)
    filterMid = audioCtx.createBiquadFilter();
    filterMid.type = 'peaking';
    filterMid.frequency.value = 1000;
    filterMid.Q.value = 0.8;
    filterMid.gain.value = 1.5; // Slight voice boost

    // Treble/Clarity Filter (definition around 8kHz)
    filterTreble = audioCtx.createBiquadFilter();
    filterTreble.type = 'highshelf';
    filterTreble.frequency.value = 8000;
    filterTreble.gain.value = 3.0; // Clearer highs

    // Dynamic Range Compressor (limits peak levels, reduces distortion, matches studio mastering)
    compressor = audioCtx.createDynamicsCompressor();
    compressor.threshold.value = -12; // dB
    compressor.knee.value = 30; // dB
    compressor.ratio.value = 3;
    compressor.attack.value = 0.003; // seconds
    compressor.release.value = 0.08; // seconds

    // Connect nodes in series: source -> Bass -> Mid -> Treble -> Compressor -> Output
    sourceNode.connect(filterBass);
    filterBass.connect(filterMid);
    filterMid.connect(filterTreble);
    filterTreble.connect(compressor);
    compressor.connect(audioCtx.destination);

    isAudioPipelineInitialized = true;
    console.log('[HiFi-Pipeline] Web Audio dynamic processing chain activated successfully.');
  } catch (e) {
    console.warn('[HiFi-Pipeline] Initialization deferred or blocked (e.g. CORS or user gesture required)', e);
  }
}

function ensureAudioCtxActive() {
  initAudioPipeline();
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(()=>{});
  }
}

// Preset mapping
const EQ_PRESETS = {
  balanced: { bass: 4.0, mid: 1.5, treble: 3.0, compress: true },
  'bass-boost': { bass: 8.5, mid: 0.5, treble: 2.0, compress: true },
  'vocal-boost': { bass: -1.0, mid: 4.5, treble: 3.5, compress: true },
  'treble-boost': { bass: 0.5, mid: 1.0, treble: 7.0, compress: true },
  flat: { bass: 0.0, mid: 0.0, treble: 0.0, compress: false }
};

function applyEQPreset(presetName) {
  ensureAudioCtxActive();
  const preset = EQ_PRESETS[presetName] || EQ_PRESETS.balanced;
  if (!isAudioPipelineInitialized) return;
  
  // Set filter gains smoothly
  if (filterBass) filterBass.gain.setTargetAtTime(preset.bass, audioCtx.currentTime, 0.1);
  if (filterMid) filterMid.gain.setTargetAtTime(preset.mid, audioCtx.currentTime, 0.1);
  if (filterTreble) filterTreble.gain.setTargetAtTime(preset.treble, audioCtx.currentTime, 0.1);
  
  if (compressor) {
    const thresh = preset.compress ? -12 : 0;
    compressor.threshold.setTargetAtTime(thresh, audioCtx.currentTime, 0.1);
  }
  console.log(`[HiFi-Pipeline] EQ preset applied: ${presetName}`);
}

function toggleAudioEnhancer(enabled) {
  ensureAudioCtxActive();
  if (!isAudioPipelineInitialized) return;
  if (enabled) {
    const selectEl = $('#eq-preset-select');
    applyEQPreset(selectEl ? selectEl.value : 'balanced');
  } else {
    applyEQPreset('flat');
  }
}

// Prime AudioContext on first interaction
['click', 'keydown', 'touchstart'].forEach(evt => {
  document.addEventListener(evt, () => {
    ensureAudioCtxActive();
  }, { once: true });
});

/* ═══════ API ═══════ */
async function api(method, path, body) {
  const h = { 'Content-Type': 'application/json' };
  if (state.token) h['Authorization'] = `Bearer ${state.token}`;
  const opts = { method, headers: h };
  if (body && method !== 'GET') opts.body = JSON.stringify(body);
  try {
    const res = await fetch(path, opts);
    if (res.status === 401) { logout(); showToast('Session expired', 'error'); return null; }
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      let detail = res.statusText;
      try {
        const parsed = JSON.parse(text);
        if (parsed && parsed.detail) detail = parsed.detail;
      } catch (_) {}
      
      let msg = 'Request failed';
      if (detail) {
        if (typeof detail === 'string') {
          msg = detail;
        } else if (Array.isArray(detail)) {
          msg = detail.map(err => {
            const field = err.loc ? err.loc[err.loc.length - 1] : '';
            return field ? `${field}: ${err.msg}` : err.msg;
          }).join(', ');
        }
      }
      const err = new Error(msg);
      // Mark as client error if it's a 4xx error (except 401 which is already handled)
      if (res.status >= 400 && res.status < 500) {
        err.isClientError = true;
      }
      throw err;
    }
    if (res.status === 204) return null;
    
    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await res.json();
    }
    
    // Fallback text check
    const text = await res.text();
    if (text.trim().startsWith('<!DOCTYPE') || text.trim().startsWith('<html')) {
      throw new Error('Server returned HTML instead of JSON. The backend server might still be starting up or is offline.');
    }
    try {
      return JSON.parse(text);
    } catch (_) {
      throw new Error('Server response was not valid JSON.');
    }
  } catch (e) {
    // Stop all technical/network/parsing error notifications from coming to the user.
    // They are logged in console and hidden from the users. Only client input errors (4xx) are shown.
    if (e && e.isClientError) {
      showToast(e.message || 'Request failed', 'error');
    }
    console.error(`[API] ${method} ${path}`, e);
    return null;
  }
}
api.get = p => api('GET', p);
api.post = (p, b) => api('POST', p, b);
api.put = (p, b) => api('PUT', p, b);
api.delete = p => api('DELETE', p);

/* ═══════ TOAST ═══════ */
function showToast(message, type = 'info') {
  const c = $('#toast-container'); if (!c) return;
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.innerHTML = `<span>${escapeHtml(message)}</span><button class="toast-close" onclick="this.parentElement.remove()">✕</button>`;
  c.appendChild(t);
  setTimeout(() => { t.style.animation = 'toastOut .3s ease forwards'; t.addEventListener('animationend', () => t.remove()); }, 3500);
}

/* ═══════ ROUTER ═══════ */
function navigateTo(hash) { window.location.hash = hash; }

function handleRoute() {
  const hash = window.location.hash || '#/';
  const [route, param] = hash.replace('#/', '').split('/');

  if (['dashboard','room','profile'].includes(route) && !state.token) {
    showAuthModal('login'); navigateTo('#/'); return;
  }
  if (route === '' && state.token) {
    navigateTo('#/dashboard'); return;
  }
  $$('.page').forEach(el => el.style.display = 'none');
  $('#global-loader').style.display = 'none';

  // Toggle global play bar visibility
  const pb = $('#global-player-bar');
  if (pb) {
    if (state.token && route !== '') {
      pb.style.display = 'flex';
      document.body.classList.add('has-playbar');
    } else {
      pb.style.display = 'none';
      document.body.classList.remove('has-playbar');
    }
  }

  switch (route) {
    case '': $('#landing-page').style.display = ''; break;
    case 'dashboard':
      $('#dashboard-page').style.display = '';
      switchSubpage(state.currentSubpage || 'home');
      loadRooms(); loadHomeSections(); fetchUserLikedSongsList();
      break;
    case 'room':
      if (param) { $('#room-page').style.display = ''; enterRoom(param); }
      else navigateTo('#/dashboard');
      break;
    case 'profile':
      $('#profile-page').style.display = ''; renderProfile();
      break;
    default: $('#landing-page').style.display = '';
  }
}
window.addEventListener('hashchange', handleRoute);

/* ═══════ AUTH ═══════ */
function showAuthModal(tab = 'login') {
  const m = $('#auth-modal'); if (!m) return;
  m.style.display = 'flex';
  $$('.auth-tab').forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected','false'); });
  $$('.auth-form-panel').forEach(f => f.classList.remove('active'));
  const btn = $(`[data-tab="${tab}"]`);
  const panel = $(`#${tab}-form-panel`);
  if (btn) { btn.classList.add('active'); btn.setAttribute('aria-selected','true'); }
  if (panel) panel.classList.add('active');
}

function hideAuthModal() { const m = $('#auth-modal'); if (m) m.style.display = 'none'; }

async function handleLogin(e) {
  e.preventDefault();
  const email = $('#login-email').value.trim();
  const password = $('#login-password').value;
  if (!email || !password) { showToast('Fill in all fields', 'error'); return; }
  const data = await api.post('/api/auth/login', { email, password });
  if (!data) return;
  state.token = data.access_token; state.user = data.user;
  
  const remember = $('#login-remember')?.checked;
  if (remember) {
    localStorage.setItem('vynce_token', data.access_token);
    sessionStorage.removeItem('vynce_token');
  } else {
    sessionStorage.setItem('vynce_token', data.access_token);
    localStorage.removeItem('vynce_token');
  }
  
  hideAuthModal();
  showToast(`Welcome back, ${state.user?.username || 'friend'}!`, 'success');
  navigateTo('#/dashboard');
}

async function handleRegister(e) {
  e.preventDefault();
  const username = $('#register-username').value.trim();
  const email = $('#register-email').value.trim();
  const password = $('#register-password').value;
  if (!username || !email || !password) { showToast('Fill in all fields', 'error'); return; }
  if (password.length < 6) { showToast('Password must be at least 6 characters', 'error'); return; }
  const data = await api.post('/api/auth/register', { username, email, password });
  if (!data) return;
  state.token = data.access_token; state.user = data.user;
  
  const remember = $('#register-remember')?.checked;
  if (remember) {
    localStorage.setItem('vynce_token', data.access_token);
    sessionStorage.removeItem('vynce_token');
  } else {
    sessionStorage.setItem('vynce_token', data.access_token);
    localStorage.removeItem('vynce_token');
  }
  
  hideAuthModal();
  showToast('Welcome to Vynce!', 'success');
  navigateTo('#/dashboard');
}

async function loadCurrentUser() {
  const data = await api.get('/api/auth/me');
  if (data) { state.user = data; updateUserUI(); }
}

function logout() {
  state.token = null; state.user = null;
  state.isPlaying = false;
  audio.pause();
  audio.src = '';
  updatePlaybackUI();
  localStorage.removeItem('vynce_token');
  sessionStorage.removeItem('vynce_token');
  if (state.ws) { state.ws.close(); state.ws = null; }
  navigateTo('#/');
}

function updateUserUI() {
  if (!state.user) return;
  const n = $('#user-display-name');
  if (n) n.textContent = state.user.username;
  const a = $('#user-avatar');
  if (a) { a.style.background = nameColor(state.user.username); a.textContent = state.user.username[0].toUpperCase(); }
}

function renderProfile() {
  if (!state.user) return;
  const u = $('#profile-username'); if (u) u.textContent = state.user.username;
  const e = $('#profile-email'); if (e) e.textContent = state.user.email;
  const a = $('#profile-avatar');
  if (a) { a.style.background = nameColor(state.user.username); a.textContent = state.user.username[0].toUpperCase(); }
  
  // Set tab active state
  $$('.profile-tab').forEach(t => t.classList.remove('active'));
  $$('.profile-tab-panel').forEach(p => p.classList.remove('active'));
  const firstTab = $('.profile-tab[data-tab="playlists"]');
  if (firstTab) firstTab.classList.add('active');
  const playlistsTab = $('#profile-playlists-tab');
  if (playlistsTab) playlistsTab.classList.add('active');

  loadPlaylistsProfile();
}

/* ═══════ ROOMS ═══════ */
async function loadRooms() {
  const data = await api.get('/api/rooms');
  if (!data) return;
  state.rooms = Array.isArray(data) ? data : (data.rooms || []);
  renderRoomCards(state.rooms, '#public-rooms-grid');
}

async function createRoom(name, isPublic = true) {
  const data = await api.post('/api/rooms', { name, is_public: isPublic });
  if (!data) return;
  showToast('Room created!', 'success');
  navigateTo(`#/room/${data.code}`);
}

async function enterRoom(code) {
  if (state.ws) { state.ws.close(); state.ws = null; }
  const data = await api.get(`/api/rooms/${code}`);
  if (!data) { showToast('Room not found', 'error'); navigateTo('#/dashboard'); return; }
  state.currentRoom = data;
  const n = $('#room-name-display'); if (n) n.textContent = data.name;
  const c = $('#invite-code-display'); if (c) c.textContent = data.code;
  connectToRoom(code);
}

function leaveRoom() {
  if (state.ws) { state.ws.close(); state.ws = null; }
  state.currentRoom = null; state.currentTrack = null; state.queue = [];
  state.isPlaying = false; audio.pause();
  navigateTo('#/dashboard');
}

function renderRoomCards(rooms, sel) {
  const c = $(sel); if (!c) return;
  c.innerHTML = '';
  if (!rooms.length) { c.innerHTML = '<p class="empty-hint">No rooms yet — create one!</p>'; return; }
  rooms.forEach(r => {
    const card = document.createElement('div');
    card.className = 'room-card';
    card.innerHTML = `
      <div class="room-card-name">${escapeHtml(r.name)}</div>
      <div class="room-card-listeners">${r.listener_count ?? 0} listening</div>
      <div class="room-card-track">${r.current_track ? escapeHtml(r.current_track.title) : 'No track playing'}</div>
      <div class="room-card-actions">
        <button class="btn btn-primary btn-sm join-btn">Join Room</button>
      </div>`;
    card.querySelector('.join-btn').addEventListener('click', () => navigateTo(`#/room/${r.code}`));
    c.appendChild(card);
  });
}

/* ═══════ WEBSOCKET ═══════ */
let wsRetries = 0, wsHeartbeat = null;

function connectToRoom(code) {
  if (state.ws?.readyState <= WebSocket.OPEN) state.ws.close();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/${code}?token=${encodeURIComponent(state.token)}`);
  ws.onopen = () => { wsRetries = 0; startHeartbeat(); };
  ws.onmessage = e => { try { handleWSMessage(JSON.parse(e.data)); } catch(err) { console.error('[WS]', err); } };
  ws.onclose = () => { stopHeartbeat(); if (state.currentRoom?.code === code) attemptReconnect(code); };
  ws.onerror = err => console.error('[WS] Error', err);
  state.ws = ws;
}

function handleWSMessage(msg) {
  const d = msg.data || msg;
  switch(msg.type) {
    case 'room_state':
      if (d.current_track) loadTrack(d.current_track, d.position || 0);
      if (d.is_playing) { audio.play().catch(()=>{}); state.isPlaying = true; }
      if (d.queue) { state.queue = d.queue; renderQueue(); renderExpandedQueue(); }
      if (d.users) renderListeners(d.users);
      updatePlaybackUI(); break;
    case 'user_joined': showToast(`${escapeHtml(d.username)} joined`, 'info'); updateLC(d.listener_count); break;
    case 'user_left': showToast(`${escapeHtml(d.username)} left`, 'info'); updateLC(d.listener_count); break;
    case 'play_track': loadTrack(d.track, 0); audio.play().catch(()=>{}); state.isPlaying = true; updatePlaybackUI(); break;
    case 'sync': handleSync(d); break;
    case 'pause': audio.pause(); state.isPlaying = false; updatePlaybackUI(); break;
    case 'resume': audio.play().catch(()=>{}); state.isPlaying = true; updatePlaybackUI(); break;
    case 'seek': audio.currentTime = d.position; break;
    case 'queue_update': state.queue = d.queue || []; renderQueue(); renderExpandedQueue(); break;
    case 'chat_message': appendChatMessage(d); break;
    case 'error': showToast(d.message || 'Error', 'error'); break;
    case 'pong': break;
  }
}
function handleSync(d) { if(!audio.src || !state.currentTrack) return; if(Math.abs(audio.currentTime - d.position) > 0.5) audio.currentTime = d.position; }
function sendWS(type, data = {}) { if(state.ws?.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify({type, data})); }
function startHeartbeat() { stopHeartbeat(); wsHeartbeat = setInterval(() => { if(state.ws?.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify({type:'ping'})); }, 30000); }
function stopHeartbeat() { if(wsHeartbeat) { clearInterval(wsHeartbeat); wsHeartbeat = null; } }
function attemptReconnect(code) { if(wsRetries >= 5) { showToast('Lost connection', 'error'); return; } const delay = Math.min(1000*2**wsRetries,16000); wsRetries++; setTimeout(() => connectToRoom(code), delay); }
function updateLC(c) { const el = $('#listener-count-display'); if(el && c!=null) el.textContent = c; }

/* ═══════ AUDIO PLAYER ═══════ */
function loadTrack(track, startAt = 0, isRestore = false) {
  if (!track?.stream_url) return;
  if (state.currentTrack && state.currentTrack.id !== track.id) {
    state.history.push(state.currentTrack);
    if (state.history.length > 50) state.history.shift();
  }
  state.currentTrack = track;
  try { audio.src = track.stream_url; audio.currentTime = startAt; } catch(e) { showToast('Could not load track', 'error'); return; }
  const t = $('#player-track-title'); if(t) t.textContent = track.title || 'Unknown';
  const a = $('#player-track-artist'); if(a) a.textContent = track.artist || 'Unknown';
  const d = $('#time-total'); if(d) d.textContent = formatTime(track.duration);
  const img = $('#player-album-art');
  if(img) { img.src = track.album_art || ''; img.alt = track.title || ''; }
  const bar = $('#progress-fill'); if(bar) bar.style.width = '0%';
  const cur = $('#time-current'); if(cur) cur.textContent = '0:00';

  updateExpandedPlayerUI();
  loadLyricsAndRelated();
  if (!isRestore) {
    logHistoryToBackend(track);
  }
  // Store track in localStorage to preserve on tab close
  try {
    localStorage.setItem('vynce_last_track', JSON.stringify(track));
    localStorage.setItem('vynce_last_time', startAt.toString());
  } catch(e) {
    console.error("[Vynce] Error saving last track:", e);
  }
}

function togglePlay() {
  if(!audio.src) return;
  if(state.isPlaying) { audio.pause(); state.isPlaying = false; if(state.currentRoom) sendWS('pause'); }
  else { audio.play().catch(e => showToast('Click play again — browser blocked autoplay', 'info')); state.isPlaying = true; if(state.currentRoom) sendWS('resume'); }
  updatePlaybackUI();
}

function seekTo(pos) { if(!audio.src) return; audio.currentTime = pos; if(state.currentRoom) sendWS('seek', {position:pos}); }
function setVolume(v) { state.volume = Math.max(0,Math.min(1,v)); audio.volume = state.volume; localStorage.setItem('vynce_volume', state.volume); updateVolumeUI(); }

async function playNext() {
  if(!state.queue.length) {
    if (state.currentTrack) {
      try {
        const res = await api.get(`/api/music/song/${state.currentTrack.id}/similar?limit=15`);
        if (res && res.tracks && res.tracks.length) {
          // Exclude tracks in local history (last 15 tracks played) and current track
          const recentlyPlayed = new Set(state.history.slice(-15).map(t => t.id));
          recentlyPlayed.add(state.currentTrack.id);
          
          const pool = res.tracks.filter(t => !recentlyPlayed.has(t.id));
          
          let next;
          if (pool.length > 0) {
            // Pick the first fresh track
            next = pool[0];
          } else {
            // Fallback: if all similar songs were played recently, pick a random one from similar list to break loop
            const randIdx = Math.floor(Math.random() * res.tracks.length);
            next = res.tracks[randIdx];
          }
          
          playTrack(next);
          return;
        }
      } catch (err) {
        console.error('[Autoplay] Error fetching similar tracks:', err);
      }
    }
    showToast('Queue is empty', 'info');
    return;
  }
  const next = state.queue.shift();
  if(state.currentRoom) sendWS('play_track', {track:next});
  else {
    loadTrack(next);
    audio.play().catch(()=>{});
    state.isPlaying = true;
    updatePlaybackUI();
  }
  renderQueue();
}

async function playPrev() {
  if (state.currentRoom) {
    sendWS('prev_track');
    return;
  }
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  if (!state.history.length) {
    if (audio.src) audio.currentTime = 0;
    return;
  }
  const prev = state.history.pop();
  if (state.currentTrack) {
    state.queue.unshift(state.currentTrack);
    renderQueue();
  }
  loadTrack(prev);
  audio.play().catch(()=>{});
  state.isPlaying = true;
  updatePlaybackUI();
}

let lastSavedTime = 0;
audio.addEventListener('timeupdate', () => {
  const dur = audio.duration || state.currentTrack?.duration || 0; if(!dur) return;
  const pct = (audio.currentTime/dur)*100;
  const bar = $('#progress-fill'); if(bar) bar.style.width = `${pct}%`;
  const thumb = $('#progress-thumb'); if(thumb) thumb.style.left = `${pct}%`;
  const cur = $('#time-current'); if(cur) cur.textContent = formatTime(audio.currentTime);

  const expBar = $('#expanded-progress-fill'); if(expBar) expBar.style.width = `${pct}%`;
  const expThumb = $('#expanded-progress-thumb'); if(expThumb) expThumb.style.left = `${pct}%`;
  const expCur = $('#expanded-time-current'); if(expCur) expCur.textContent = formatTime(audio.currentTime);

  if (state.currentTrack && Math.abs(audio.currentTime - lastSavedTime) >= 1) {
    try {
      localStorage.setItem('vynce_last_time', audio.currentTime.toString());
      lastSavedTime = audio.currentTime;
    } catch(e) {}
  }
});
audio.addEventListener('ended', () => { state.isPlaying = false; updatePlaybackUI(); playNext(); });
audio.addEventListener('error', () => { showToast('Playback error — skipping', 'error'); playNext(); });

function updatePlaybackUI() {
  const btn = $('#btn-play-pause'); if(!btn) return;
  const play = btn.querySelector('.icon-play');
  const pause = btn.querySelector('.icon-pause');
  if(play) play.style.display = state.isPlaying ? 'none' : '';
  if(pause) pause.style.display = state.isPlaying ? '' : 'none';

  // Sync expanded player play/pause button
  const expBtn = $('#btn-player-play-pause');
  if (expBtn) {
    const expPlay = expBtn.querySelector('.icon-play');
    const expPause = expBtn.querySelector('.icon-pause');
    if (expPlay) expPlay.style.display = state.isPlaying ? 'none' : '';
    if (expPause) expPause.style.display = state.isPlaying ? '' : 'none';
  }
}
function updateVolumeUI() {
  const s = $('#volume-slider'); if(s) s.value = Math.round(state.volume * 100);
  const expVol = $('#expanded-volume-slider'); if(expVol) expVol.value = Math.round(state.volume * 100);
}

function renderQueue() {
  const c = $('#queue-list'); if(!c) return;
  c.innerHTML = '';
  if(!state.queue.length) { c.innerHTML = '<p class="empty-hint">Queue is empty</p>'; return; }
  state.queue.forEach((t,i) => {
    const d = document.createElement('div'); d.className = 'queue-item';
    d.style.cursor = 'pointer';
    d.innerHTML = `
      <img class="queue-item-art" src="${escapeHtml(t.album_art||'')}" alt="" onerror="this.style.display='none'" />
      <div class="queue-item-info"><span class="queue-item-title">${escapeHtml(t.title)}</span><span class="queue-item-artist">${escapeHtml(t.artist)}</span></div>
      <span style="font-size:12px;color:var(--text-3);margin-right:8px;">${formatTime(t.duration)}</span>
      <button class="remove-queue-btn" title="Remove from Queue">&times;</button>`;
    d.querySelector('.remove-queue-btn').addEventListener('click', e => {
      e.stopPropagation();
      removeFromQueue(i);
    });
    d.addEventListener('click', () => {
      if (state.currentRoom) {
        sendWS('remove_from_queue', { index: i });
        sendWS('play_track', { track: t });
      } else {
        const chosen = state.queue.splice(i, 1)[0];
        playTrack(chosen);
        renderQueue();
        renderExpandedQueue();
      }
    });
    c.appendChild(d);
  });
}

/* ═══════ SEARCH ═══════ */
async function searchMusic(query) {
  if(!query.trim()) return;
  const data = await api.get(`/api/music/search?q=${encodeURIComponent(query)}&source=all&limit=30`);
  if(!data) return;
  return data.tracks || [];
}

// Search History Management
function saveSearchToHistory(query) {
  if (!query || !query.trim() || query.trim().length < 2) return;
  const q = query.trim();
  let history = [];
  try {
    history = JSON.parse(localStorage.getItem('vynce_recent_searches') || '[]');
  } catch (e) {
    history = [];
  }
  
  // Filter out the search query if it already exists, and insert at front
  history = history.filter(item => item.toLowerCase() !== q.toLowerCase());
  history.unshift(q);
  if (history.length > 5) history = history.slice(0, 5);
  
  localStorage.setItem('vynce_recent_searches', JSON.stringify(history));
  renderSearchHistory();
}

function renderSearchHistory() {
  const dropdown = $('#search-history-dropdown');
  const listEl = $('#search-history-list');
  if (!dropdown || !listEl) return;
  
  let history = [];
  try {
    history = JSON.parse(localStorage.getItem('vynce_recent_searches') || '[]');
  } catch (e) {
    history = [];
  }
  
  if (!history.length) {
    dropdown.style.display = 'none';
    return;
  }
  
  listEl.innerHTML = '';
  history.forEach(item => {
    const row = document.createElement('div');
    row.className = 'search-history-item';
    row.innerHTML = `
      <span class="search-history-item-text"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="btn-svg" style="width: 14px; height: 14px; margin-right: 6px;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>${escapeHtml(item)}</span>
      <button class="remove-history-item-btn" title="Remove">&times;</button>
    `;
    
    // Clicking on text triggers a search
    row.querySelector('.search-history-item-text').addEventListener('click', (e) => {
      e.stopPropagation();
      const input = $('#search-music-input');
      if (input) {
        input.value = item;
        
        // Trigger dashboard search
        const resultsSec = $('#search-results-section');
        const resultsGrid = $('#search-results');
        if (resultsSec && resultsGrid) {
          resultsSec.style.display = '';
          resultsGrid.innerHTML = '<div class="track-skeleton"></div><div class="track-skeleton"></div>';
          searchMusic(item).then(tracks => {
            if (tracks) renderTrackCards(tracks, '#search-results');
          });
        }
        
        // Trigger saving it back to top of history
        saveSearchToHistory(item);
      }
      dropdown.style.display = 'none';
    });
    
    // Clicking on removal button removes the item from history
    row.querySelector('.remove-history-item-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      let hist = [];
      try { hist = JSON.parse(localStorage.getItem('vynce_recent_searches') || '[]'); } catch(_) {}
      hist = hist.filter(x => x !== item);
      localStorage.setItem('vynce_recent_searches', JSON.stringify(hist));
      renderSearchHistory();
    });
    
    listEl.appendChild(row);
  });
}


async function loadTrending() {
  const data = await api.get('/api/music/trending?limit=20');
  if(!data) return;
  renderTrackCards(data.tracks || [], '#trending-tracks');
}

function renderTrackCards(tracks, sel) {
  const c = $(sel); if(!c) return;
  c.innerHTML = '';
  if(!tracks.length) { c.innerHTML = '<p class="empty-hint">No tracks found</p>'; return; }
  const isSearch = (sel === '#search-results');
  tracks.forEach((t, i) => {
    const card = document.createElement('div');
    card.className = 'track-card' + (isSearch ? '' : ' suggested-card');
    card.style.animationDelay = `${i*0.04}s`;
    card.innerHTML = `
      <div style="position:relative; width:100%; aspect-ratio:1; overflow:hidden; border-radius:var(--radius);">
        <img class="track-card-art" src="${escapeHtml(t.album_art||'')}" alt="${escapeHtml(t.title)}" loading="lazy" onerror="this.style.background='linear-gradient(135deg,#1a1a3e,#0a0a14)'" />
        <div class="track-card-overlay">
          <div class="overlay-play-btn" title="Play"><svg viewBox="0 0 24 24" fill="currentColor" style="width:20px; height:20px; display:block;"><polygon points="5 3 19 12 5 21 5 3"/></svg></div>
          <div class="overlay-details">
            <span class="overlay-title">${escapeHtml(t.title)}</span>
            <span class="overlay-artist">${escapeHtml(t.artist)}</span>
          </div>
          <button class="overlay-queue-btn" title="Add to Queue">+</button>
        </div>
      </div>
      <div class="track-card-info">
        <span class="track-card-title">${escapeHtml(t.title)}</span>
        <span class="track-card-artist">${escapeHtml(t.artist)}</span>
      </div>
      <div class="track-card-actions">
        <button class="btn btn-primary btn-sm play-btn" style="display: flex; align-items: center; justify-content: center; gap: 4px;"><svg viewBox="0 0 24 24" fill="currentColor" style="width:12px; height:12px; display:inline-block;"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play</button>
        <button class="btn btn-ghost btn-sm queue-btn">+ Queue</button>
      </div>`;
    card.querySelector('.play-btn').addEventListener('click', e => { e.stopPropagation(); playTrack(t); });
    card.querySelector('.queue-btn').addEventListener('click', e => { e.stopPropagation(); addToQueue(t); });
    card.querySelector('.overlay-play-btn').addEventListener('click', e => { e.stopPropagation(); playTrack(t); });
    card.querySelector('.overlay-queue-btn').addEventListener('click', e => { e.stopPropagation(); addToQueue(t); });
    card.addEventListener('click', () => playTrack(t));
    c.appendChild(card);
  });
}

function renderSearchResultsList(tracks, sel) {
  const c = $(sel); if(!c) return;
  c.innerHTML = '';
  if(!tracks.length) { c.innerHTML = '<p class="empty-hint" style="padding:12px">No results found</p>'; return; }
  tracks.forEach(t => {
    const item = document.createElement('div');
    item.className = 'search-result-item';
    item.innerHTML = `
      <img class="search-result-art" src="${escapeHtml(t.album_art||'')}" alt="" onerror="this.style.background='#1a1a3e'" />
      <div class="search-result-info">
        <span class="search-result-title">${escapeHtml(t.title)}</span>
        <span class="search-result-artist">${escapeHtml(t.artist)} · ${formatTime(t.duration)}</span>
      </div>
      <div class="search-result-actions">
        <button class="btn btn-ghost play-btn" title="Play">▶</button>
        <button class="btn btn-ghost queue-btn" title="Add to queue">+</button>
      </div>`;
    item.querySelector('.play-btn').addEventListener('click', e => { e.stopPropagation(); playTrack(t); });
    item.querySelector('.queue-btn').addEventListener('click', e => { e.stopPropagation(); addToQueue(t); });
    item.addEventListener('click', () => playTrack(t));
    c.appendChild(item);
  });
}

function playTrack(track) {
  if(state.currentRoom) sendWS('play_track', {track});
  else {
    loadTrack(track);
    audio.play().catch(()=>{});
    state.isPlaying = true;
    updatePlaybackUI();
  }
}

function addToQueue(track) {
  state.queue.push(track); renderQueue();
  if(state.currentRoom) sendWS('queue_update', {queue:state.queue});
  showToast(`Added "${track.title}" to queue`, 'success');
}

function removeFromQueue(index) {
  if (state.currentRoom) {
    sendWS('remove_from_queue', { index: index });
  } else {
    if (index >= 0 && index < state.queue.length) {
      const removed = state.queue.splice(index, 1)[0];
      renderQueue();
      renderExpandedQueue();
      showToast(`Removed "${removed.title}" from queue`, 'info');
    }
  }
}

/* ═══════ CHAT ═══════ */
function appendChatMessage(msg) {
  const c = $('#chat-messages'); if(!c) return;
  const color = nameColor(msg.username||'anon');
  const isOwn = state.user && msg.username === state.user.username;
  const el = document.createElement('div'); el.className = `chat-message ${isOwn?'chat-own':''}`;
  el.innerHTML = `
    <div class="chat-avatar" style="background:${color}">${escapeHtml((msg.username||'?')[0].toUpperCase())}</div>
    <div class="chat-bubble">
      <span class="chat-username" style="color:${color}">${escapeHtml(msg.username||'Unknown')}</span>
      <span class="chat-text">${escapeHtml(msg.text||msg.message||'')}</span>
    </div>`;
  c.appendChild(el);
  c.scrollTop = c.scrollHeight;
}

function renderListeners(users) {
  const c = $('#listeners-list'); if(!c) return; c.innerHTML = '';
  const lc = $('#listener-count-display'); if(lc) lc.textContent = users.length;
  users.forEach(u => {
    const color = nameColor(u.username);
    const el = document.createElement('div'); el.className = 'listener-item';
    el.innerHTML = `<div class="listener-avatar" style="background:${color}">${escapeHtml(u.username[0].toUpperCase())}</div><span>${escapeHtml(u.username)}</span>`;
    c.appendChild(el);
  });
}

/* ═══════ INIT ═══════ */
document.addEventListener('DOMContentLoaded', () => {
  // Auth
  $$('.auth-tab').forEach(tab => tab.addEventListener('click', () => showAuthModal(tab.dataset.tab)));
  const authModal = $('#auth-modal');
  if(authModal) authModal.addEventListener('click', e => { if(e.target === authModal) hideAuthModal(); });
  $('#btn-auth-close')?.addEventListener('click', hideAuthModal);
  $('#btn-switch-to-register')?.addEventListener('click', () => showAuthModal('register'));
  $('#btn-switch-to-login')?.addEventListener('click', () => showAuthModal('login'));
  $('#login-form')?.addEventListener('submit', handleLogin);
  $('#register-form')?.addEventListener('submit', handleRegister);

  // Landing
  $('#btn-nav-login')?.addEventListener('click', () => showAuthModal('login'));
  $('#btn-nav-signup')?.addEventListener('click', () => showAuthModal('register'));
  $('#btn-hero-create-room')?.addEventListener('click', () => { if(state.token) navigateTo('#/dashboard'); else showAuthModal('register'); });
  $('#btn-hero-explore')?.addEventListener('click', () => { if(state.token) navigateTo('#/dashboard'); else showAuthModal('login'); });

  // Dashboard
  const menuToggle = $('#btn-user-menu-toggle'), dropdown = $('#user-dropdown');
  if(menuToggle && dropdown) {
    menuToggle.addEventListener('click', () => { dropdown.style.display = dropdown.style.display==='none'?'block':'none'; });
    document.addEventListener('click', e => { if(!menuToggle.contains(e.target) && !dropdown.contains(e.target)) dropdown.style.display='none'; });
  }
  $('#btn-dropdown-profile')?.addEventListener('click', () => navigateTo('#/profile'));
  $('#btn-dropdown-logout')?.addEventListener('click', logout);

  // Create room
  const createRoomModal = $('#create-room-modal');
  $('#btn-open-create-room')?.addEventListener('click', () => { if(createRoomModal) createRoomModal.style.display = 'flex'; });
  $('#btn-create-room-close')?.addEventListener('click', () => { if(createRoomModal) createRoomModal.style.display = 'none'; });
  $('#create-room-form')?.addEventListener('submit', e => {
    e.preventDefault();
    const name = $('#room-name-input').value.trim();
    const isPublic = $('#room-visibility-toggle')?.checked ?? true;
    if(name) { createRoom(name, isPublic); if(createRoomModal) createRoomModal.style.display = 'none'; }
  });

  // Sub-navigation clicks
  $$('.sub-nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      switchSubpage(btn.dataset.subpage);
    });
  });
  
  // Sub-navigation arrows
  $('#btn-sub-nav-prev')?.addEventListener('click', () => navigateSubpage(-1));
  $('#btn-sub-nav-next')?.addEventListener('click', () => navigateSubpage(1));

  // Dashboard search
  const searchInput = $('#search-music-input');
  const searchHistoryDropdown = $('#search-history-dropdown');
  const debouncedDashSearch = debounce(async q => {
    if(q.length < 2) { 
      $('#search-results-section').style.display = 'none'; 
      switchSubpage(state.currentSubpage || 'home');
      return; 
    }
    const tracks = await searchMusic(q);
    if(tracks && tracks.length) {
      // Hide all subpages when search results are shown
      $$('.subpage-container').forEach(el => el.style.display = 'none');
      $('#search-results-section').style.display = '';
      renderTrackCards(tracks, '#search-results');
      saveSearchToHistory(q);
    }
  }, 400);



  if(searchInput) {
    searchInput.addEventListener('input', e => {
      const val = e.target.value;
      if (!val.trim()) {
        renderSearchHistory();
        const history = JSON.parse(localStorage.getItem('vynce_recent_searches') || '[]');
        if (history.length > 0 && searchHistoryDropdown) {
          searchHistoryDropdown.style.display = 'block';
        }
        $('#search-results-section').style.display = 'none';
        switchSubpage(state.currentSubpage || 'home');
      } else {
        if (searchHistoryDropdown) searchHistoryDropdown.style.display = 'none';
        debouncedDashSearch(val);
      }
    });
    searchInput.addEventListener('focus', () => {
      if (!searchInput.value.trim()) {
        renderSearchHistory();
        const history = JSON.parse(localStorage.getItem('vynce_recent_searches') || '[]');
        if (history.length > 0 && searchHistoryDropdown) {
          searchHistoryDropdown.style.display = 'block';
        }
      }
    });
    searchInput.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!searchInput.value.trim()) {
        renderSearchHistory();
        const history = JSON.parse(localStorage.getItem('vynce_recent_searches') || '[]');
        if (history.length > 0 && searchHistoryDropdown) {
          searchHistoryDropdown.style.display = 'block';
        }
      }
    });
    searchInput.addEventListener('keydown', e => {
      if(e.key === 'Enter') {
        e.preventDefault();
        debouncedDashSearch(searchInput.value);
        if (searchHistoryDropdown) searchHistoryDropdown.style.display = 'none';
      }
    });
  }

  // Clear search history
  $('#btn-clear-search-history')?.addEventListener('click', (e) => {
    e.stopPropagation();
    localStorage.removeItem('vynce_recent_searches');
    if (searchHistoryDropdown) searchHistoryDropdown.style.display = 'none';
  });

  // Close search history dropdown on click outside
  document.addEventListener('click', (e) => {
    const searchBox = $('.search-box');
    if (searchBox && !searchBox.contains(e.target)) {
      if (searchHistoryDropdown) searchHistoryDropdown.style.display = 'none';
    }
  });

  // Genre chips
  $$('.genre-chip').forEach(chip => {
    chip.addEventListener('click', async () => {
      $$('.genre-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      const genre = chip.dataset.genre;
      const t = $('#genre-results-title'); if(t) t.textContent = chip.textContent.trim();
      const sec = $('#genre-results-section'); if(sec) sec.style.display = '';
      const c = $('#genre-results'); if(c) c.innerHTML = '<div class="track-skeleton"></div><div class="track-skeleton"></div>';
      const tracks = await searchMusic(genre);
      if(tracks) renderTrackCards(tracks, '#genre-results');
    });
  });

  // Close genre section
  $('#btn-close-genre')?.addEventListener('click', () => {
    $('#genre-results-section').style.display = 'none';
    $$('.genre-chip').forEach(c => c.classList.remove('active'));
  });

  // Room
  $('#btn-leave-room')?.addEventListener('click', leaveRoom);
  $('#btn-copy-invite')?.addEventListener('click', async () => {
    if(!state.currentRoom) return;
    try { await navigator.clipboard.writeText(state.currentRoom.code); showToast('Invite code copied!', 'success'); }
    catch { showToast('Code: ' + state.currentRoom.code, 'info'); }
  });

  // Player
  $('#btn-play-pause')?.addEventListener('click', togglePlay);
  $('#btn-next')?.addEventListener('click', playNext);
  $('#btn-prev')?.addEventListener('click', playPrev);
  const progressBar = $('#progress-bar');
  if(progressBar) progressBar.addEventListener('click', e => {
    const pct = (e.clientX - progressBar.getBoundingClientRect().left) / progressBar.offsetWidth;
    const dur = audio.duration || state.currentTrack?.duration || 0;
    if(dur) seekTo(pct * dur);
  });
  const volSlider = $('#volume-slider');
  if(volSlider) { volSlider.value = Math.round(state.volume*100); volSlider.addEventListener('input', e => setVolume(e.target.value/100)); }
  $('#btn-volume-toggle')?.addEventListener('click', () => { if(state.volume > 0) { state._prevVol = state.volume; setVolume(0); } else setVolume(state._prevVol || 0.7); });

  // Room search
  const roomSearch = $('#room-search-input');
  const debouncedRoomSearch = debounce(async q => {
    const c = $('#room-search-results');
    if(q.length < 2) { if(c) c.innerHTML = ''; return; }
    const tracks = await searchMusic(q);
    if(tracks) renderSearchResultsList(tracks, '#room-search-results');
  }, 400);
  if(roomSearch) roomSearch.addEventListener('input', e => debouncedRoomSearch(e.target.value));

  // Chat
  $('#chat-form')?.addEventListener('submit', e => {
    e.preventDefault();
    const input = $('#chat-input');
    if(input && input.value.trim()) { sendWS('chat_message', {text: input.value.trim()}); input.value = ''; }
  });

  // Profile
  $('#btn-profile-back')?.addEventListener('click', () => navigateTo('#/dashboard'));

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    if(['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
    if(e.code === 'Space') { e.preventDefault(); togglePlay(); }
    else if(e.code === 'ArrowRight' && e.shiftKey) playNext();
    else if(e.code === 'ArrowLeft' && e.shiftKey) playPrev();
    else if(e.code === 'ArrowUp') { e.preventDefault(); setVolume(state.volume+0.05); }
    else if(e.code === 'ArrowDown') { e.preventDefault(); setVolume(state.volume-0.05); }
  });

  // Voice search integration
  setupVoiceSearch('#btn-search-mic', '#search-music-input', (text) => debouncedDashSearch(text));
  setupVoiceSearch('#btn-room-search-mic', '#room-search-input', (text) => debouncedRoomSearch(text));

  // Expanded Player bar and controls integration
  const playbar = $('#global-player-bar');
  if (playbar) {
    playbar.addEventListener('click', (e) => {
      if (e.target.closest('.player-controls') || e.target.closest('.volume-wrap') || e.target.closest('.progress-bar')) {
        return;
      }
      expandPlayer();
    });
  }
  $('#btn-collapse-player')?.addEventListener('click', collapsePlayer);
  $('#btn-player-play-pause')?.addEventListener('click', togglePlay);
  $('#btn-player-next')?.addEventListener('click', playNext);
  $('#btn-player-prev')?.addEventListener('click', playPrev);
  
  const expVolSlider = $('#expanded-volume-slider');
  if (expVolSlider) expVolSlider.addEventListener('input', e => setVolume(e.target.value / 100));

  // Hi-Fi Sound Enhancer Event Listeners
  $('#toggle-audio-enhancer')?.addEventListener('change', e => {
    toggleAudioEnhancer(e.target.checked);
  });
  $('#eq-preset-select')?.addEventListener('change', e => {
    if ($('#toggle-audio-enhancer')?.checked) {
      applyEQPreset(e.target.value);
    }
  });

  const expProgressBar = $('#expanded-progress-bar');
  if (expProgressBar) {
    expProgressBar.addEventListener('click', e => {
      const pct = (e.clientX - expProgressBar.getBoundingClientRect().left) / expProgressBar.offsetWidth;
      const dur = audio.duration || state.currentTrack?.duration || 0;
      if (dur) seekTo(pct * dur);
    });
  }

  // Expanded tabs
  $$('.expanded-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.expanded-tab-btn').forEach(b => b.classList.remove('active'));
      $$('.tab-panel').forEach(p => p.classList.remove('active'));
      
      btn.classList.add('active');
      const panel = $(`#panel-${btn.dataset.tab}`);
      if (panel) panel.classList.add('active');
    });
  });

  // Like & Dislike
  $('#btn-player-like')?.addEventListener('click', toggleLikeCurrentTrack);
  $('#btn-player-dislike')?.addEventListener('click', dislikeCurrentTrack);

  // Save to playlist dropdown
  $('#btn-player-save')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const dropdown = $('#player-playlist-dropdown');
    if (dropdown) {
      const isHidden = dropdown.style.display === 'none';
      dropdown.style.display = isHidden ? 'block' : 'none';
      if (isHidden) loadDropdownPlaylists();
    }
  });
  document.addEventListener('click', (e) => {
    const dropdown = $('#player-playlist-dropdown');
    if (dropdown && !dropdown.contains(e.target) && e.target.id !== 'btn-player-save') {
      dropdown.style.display = 'none';
    }
  });

  // Create playlist from dropdown
  $('#btn-dropdown-create-playlist')?.addEventListener('click', async (e) => {
    e.stopPropagation();
    const name = prompt("Enter new playlist name:");
    if (name && name.trim()) {
      const pl = await api.post('/api/playlists', { name: name.trim(), tracks: JSON.stringify([]) });
      if (pl) {
        showToast(`Playlist "${pl.name}" created!`, "success");
        loadDropdownPlaylists();
      }
    }
  });

  // Profile tabs & create playlist
  setupProfileTabs();
  $('#btn-profile-create-playlist')?.addEventListener('click', async () => {
    const name = prompt("Enter new playlist name:");
    if (name && name.trim()) {
      const pl = await api.post('/api/playlists', { name: name.trim(), tracks: JSON.stringify([]) });
      if (pl) {
        showToast(`Playlist "${pl.name}" created!`, "success");
        loadPlaylistsProfile();
      }
    }
  });

  // Boot
  const savedToken = localStorage.getItem('vynce_token') || sessionStorage.getItem('vynce_token');
  if(savedToken) { state.token = savedToken; loadCurrentUser().then(handleRoute); }
  else handleRoute();

  // Restore last played track if user leaves and returns
  try {
    const savedTrack = localStorage.getItem('vynce_last_track');
    const savedTime = parseFloat(localStorage.getItem('vynce_last_time') || '0');
    if (savedTrack) {
      const track = JSON.parse(savedTrack);
      if (track && track.stream_url) {
        loadTrack(track, savedTime, true);
        setTimeout(() => {
          const dur = audio.duration || track.duration || 0;
          if (dur) {
            const pct = (savedTime / dur) * 100;
            const bar = $('#progress-fill'); if(bar) bar.style.width = `${pct}%`;
            const thumb = $('#progress-thumb'); if(thumb) thumb.style.left = `${pct}%`;
            const cur = $('#time-current'); if(cur) cur.textContent = formatTime(savedTime);
            
            const expBar = $('#expanded-progress-fill'); if(expBar) expBar.style.width = `${pct}%`;
            const expThumb = $('#expanded-progress-thumb'); if(expThumb) expThumb.style.left = `${pct}%`;
            const expCur = $('#expanded-time-current'); if(expCur) expCur.textContent = formatTime(savedTime);
          }
        }, 200);
      }
    }
  } catch(e) {
    console.error("[Vynce] Error restoring last track:", e);
  }

  updateVolumeUI(); updatePlaybackUI();
  console.log('[Vynce] v2 ready ✓');
});

/* ══════════════ ADDITIONAL HELPER FUNCTIONS ══════════════ */

// Voice Search
function setupVoiceSearch(btnId, inputId, searchCallback) {
  const btn = $(btnId);
  const input = $(inputId);
  if (!btn || !input) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    btn.style.display = 'none';
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = 'en-IN';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (btn.classList.contains('recording')) {
      recognition.stop();
      return;
    }
    btn.classList.add('recording');
    btn.title = "Listening... Speak now";
    recognition.start();
    showToast("Listening... Speak a song name", "info");
  });

  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    input.value = text;
    showToast(`Searching for: "${text}"`, "success");
    searchCallback(text);
  };

  recognition.onerror = (e) => {
    console.error("Speech recognition error", e);
    btn.classList.remove('recording');
    btn.title = "Search with your voice";
    showToast("Voice search failed. Please try again.", "error");
  };

  recognition.onend = () => {
    btn.classList.remove('recording');
    btn.title = "Search with your voice";
  };
}

// Expanded Player Views
function expandPlayer() {
  const ep = $('#expanded-player');
  if (!ep) return;
  ep.style.display = 'block';
  updateExpandedPlayerUI();
  loadLyricsAndRelated();
}

function collapsePlayer() {
  const ep = $('#expanded-player');
  if (ep) ep.style.display = 'none';
}

function updateExpandedPlayerUI() {
  const ep = $('#expanded-player');
  if (!ep || ep.style.display === 'none') return;
  
  const track = state.currentTrack;
  if (!track) {
    $('#expanded-track-title').textContent = "No track playing";
    $('#expanded-track-artist').textContent = "Choose a track";
    $('#expanded-album-art').src = "";
    $('#expanded-time-total').textContent = "0:00";
    return;
  }
  
  $('#expanded-track-title').textContent = track.title || 'Unknown';
  $('#expanded-track-artist').textContent = track.artist || 'Unknown';
  $('#expanded-time-total').textContent = formatTime(track.duration || audio.duration);
  
  const img = $('#expanded-album-art');
  if (img) {
    img.src = track.album_art || '';
    img.alt = track.title || '';
  }
  
  // Sync player button
  const btn = $('#btn-player-play-pause');
  if (btn) {
    const play = btn.querySelector('.icon-play');
    const pause = btn.querySelector('.icon-pause');
    if (play) play.style.display = state.isPlaying ? 'none' : '';
    if (pause) pause.style.display = state.isPlaying ? '' : 'none';
  }

  updateLikeButtonUI();

  const evSlider = $('#expanded-volume-slider');
  if (evSlider) evSlider.value = Math.round(state.volume * 100);
}

// Like/Dislike Interactions
function updateLikeButtonUI() {
  const track = state.currentTrack;
  const likeBtn = $('#btn-player-like');
  if (!likeBtn) return;
  if (track && state.likedSongs?.has(track.id)) {
    likeBtn.classList.add('active');
    likeBtn.querySelector('.icon-like-inactive').style.display = 'none';
    likeBtn.querySelector('.icon-like-active').style.display = 'inline';
  } else {
    likeBtn.classList.remove('active');
    likeBtn.querySelector('.icon-like-inactive').style.display = 'inline';
    likeBtn.querySelector('.icon-like-active').style.display = 'none';
  }
}

async function toggleLikeCurrentTrack() {
  const track = state.currentTrack;
  if (!track) return;
  const isLiked = state.likedSongs.has(track.id);
  if (isLiked) {
    const res = await api('DELETE', `/api/music/like/${track.id}`);
    if (res) {
      state.likedSongs.delete(track.id);
      showToast("Removed from Liked Songs", "success");
    }
  } else {
    const res = await api.post('/api/music/like', {
      track_id: track.id,
      track_title: track.title,
      track_artist: track.artist,
      track_album: track.album || "",
      track_album_art: track.album_art || "",
      track_stream_url: track.stream_url || ""
    });
    if (res) {
      state.likedSongs.add(track.id);
      showToast("Added to Liked Songs", "success");
    }
  }
  updateLikeButtonUI();
  if ($('#profile-page').style.display !== 'none') {
    loadLikedSongsProfile();
  }
}

async function dislikeCurrentTrack() {
  const track = state.currentTrack;
  if (!track) return;
  const res = await api.post(`/api/music/dislike?track_id=${track.id}`);
  if (res) {
    showToast("Song Disliked. Skipping...", "success");
    state.likedSongs.delete(track.id);
    updateLikeButtonUI();
    playNext();
  }
}

// Playlists dropdown options
async function loadDropdownPlaylists() {
  const listEl = $('#player-playlists-options-list');
  if (!listEl) return;
  listEl.innerHTML = '<p class="empty-hint">Loading playlists...</p>';
  
  const playlists = await api.get('/api/playlists');
  if (!playlists) return;
  
  listEl.innerHTML = '';
  if (!playlists.length) {
    listEl.innerHTML = '<p class="empty-hint">No playlists found</p>';
    return;
  }
  
  playlists.forEach(pl => {
    const item = document.createElement('div');
    item.className = 'playlist-option-item';
    item.textContent = pl.name;
    item.addEventListener('click', async () => {
      await addTrackToPlaylist(pl.id, state.currentTrack);
      $('#player-playlist-dropdown').style.display = 'none';
    });
    listEl.appendChild(item);
  });
}

async function addTrackToPlaylist(playlistId, track) {
  if (!track) return;
  const pl = await api.get(`/api/playlists/${playlistId}`);
  if (!pl) return;
  
  let tracks = [];
  try {
    tracks = JSON.parse(pl.tracks || '[]');
  } catch (e) {
    tracks = [];
  }
  
  if (tracks.some(t => t.id === track.id)) {
    showToast(`"${track.title}" is already in this playlist`, "info");
    return;
  }
  
  tracks.push(track);
  
  const res = await api.put(`/api/playlists/${playlistId}`, {
    tracks: tracks
  });
  if (res) {
    showToast(`Added to playlist "${pl.name}"`, "success");
  }
}

// Lyrics & Recommendations & Queue
async function loadLyricsAndRelated() {
  const track = state.currentTrack;
  if (!track) return;

  const lyricsTextEl = $('.lyrics-text');
  if (lyricsTextEl) {
    lyricsTextEl.textContent = "Loading lyrics...";
    try {
      const data = await api.get(`/api/music/song/${track.id}/lyrics`);
      if (data && data.lyrics) {
        lyricsTextEl.textContent = data.lyrics;
      } else {
        lyricsTextEl.textContent = "Lyrics not available for this song. Enjoy the music!";
      }
    } catch (e) {
      lyricsTextEl.textContent = "Lyrics not available for this song. Enjoy the music!";
    }
  }

  const relatedEl = $('#expanded-related-list');
  if (relatedEl) {
    relatedEl.innerHTML = '<div class="track-skeleton"></div><div class="track-skeleton"></div>';
    try {
      const data = await api.get(`/api/music/song/${track.id}/similar?limit=12`);
      if (data && data.tracks) {
        renderTracksInGrid(data.tracks, relatedEl);
      } else {
        relatedEl.innerHTML = '<p class="empty-hint">No recommendations available</p>';
      }
    } catch (e) {
      relatedEl.innerHTML = '<p class="empty-hint">Failed to load recommendations</p>';
    }
  }
  
  renderExpandedQueue();
}

function renderExpandedQueue() {
  const c = $('#expanded-queue-list');
  if (!c) return;
  c.innerHTML = '';
  
  if (state.currentTrack) {
    const curItem = document.createElement('div');
    curItem.className = 'queue-item';
    curItem.style.borderLeft = '4px solid var(--accent)';
    curItem.innerHTML = `
      <img class="queue-item-art" src="${escapeHtml(state.currentTrack.album_art||'')}" alt="" onerror="this.style.display='none'" />
      <div class="queue-item-info">
        <span class="queue-item-title">${escapeHtml(state.currentTrack.title)} (Now Playing)</span>
        <span class="queue-item-artist">${escapeHtml(state.currentTrack.artist)}</span>
      </div>
      <span style="font-size:12px;color:var(--text-3)">${formatTime(state.currentTrack.duration)}</span>
    `;
    c.appendChild(curItem);
  }
  
  if (!state.queue.length) {
    const hint = document.createElement('p');
    hint.className = 'empty-hint';
    hint.textContent = 'Queue is empty — search and add songs';
    c.appendChild(hint);
    return;
  }
  
  state.queue.forEach((t, i) => {
    const d = document.createElement('div');
    d.className = 'queue-item';
    d.style.cursor = 'pointer';
    d.innerHTML = `
      <img class="queue-item-art" src="${escapeHtml(t.album_art||'')}" alt="" onerror="this.style.display='none'" />
      <div class="queue-item-info">
        <span class="queue-item-title">${escapeHtml(t.title)}</span>
        <span class="queue-item-artist">${escapeHtml(t.artist)}</span>
      </div>
      <span style="font-size:12px;color:var(--text-3);margin-right:8px;">${formatTime(t.duration)}</span>
      <button class="remove-queue-btn" title="Remove from Queue">&times;</button>
    `;
    d.querySelector('.remove-queue-btn').addEventListener('click', e => {
      e.stopPropagation();
      removeFromQueue(i);
    });
    d.addEventListener('click', () => {
      if (state.currentRoom) {
        sendWS('remove_from_queue', { index: i });
        sendWS('play_track', { track: t });
      } else {
        const chosen = state.queue.splice(i, 1)[0];
        playTrack(chosen);
        renderQueue();
        renderExpandedQueue();
      }
    });
    c.appendChild(d);
  });
}

const subpages = ['home', 'trending', 'romantic', 'sad', 'party', 'rooms'];

function switchSubpage(page) {
  if (!subpages.includes(page)) return;
  state.currentSubpage = page;
  
  // Hide search results if switching subpages
  const searchResultsSec = $('#search-results-section');
  if (searchResultsSec) searchResultsSec.style.display = 'none';
  const searchInput = $('#search-music-input');
  if (searchInput) searchInput.value = '';

  subpages.forEach(p => {
    const el = $(`#subpage-${p}`);
    if (el) {
      el.style.display = p === page ? 'block' : 'none';
      if (p === page) el.classList.add('active');
      else el.classList.remove('active');
    }
  });

  $$('.sub-nav-btn').forEach(btn => {
    if (btn.dataset.subpage === page) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

function navigateSubpage(direction) {
  const searchResultsSec = $('#search-results-section');
  const isSearchActive = searchResultsSec && searchResultsSec.style.display !== 'none';
  
  if (isSearchActive) {
    searchResultsSec.style.display = 'none';
    const searchInput = $('#search-music-input');
    if (searchInput) searchInput.value = '';
  }
  
  const currentIndex = subpages.indexOf(state.currentSubpage || 'home');
  let nextIndex = currentIndex + direction;
  if (nextIndex < 0) nextIndex = subpages.length - 1;
  if (nextIndex >= subpages.length) nextIndex = 0;
  switchSubpage(subpages[nextIndex]);
}

// Homepage layout loading
async function loadHomeSections() {
  const recentlyPlayedSection = $('#section-recently-played');
  const forYouSection = $('#section-for-you');
  const trendingSection = $('#section-trending');
  const romanticSection = $('#section-romantic');
  const sadSection = $('#section-sad');
  const partySection = $('#section-party');
  
  if (recentlyPlayedSection) recentlyPlayedSection.innerHTML = '';
  if (forYouSection) forYouSection.innerHTML = '';
  if (trendingSection) trendingSection.innerHTML = '';
  if (romanticSection) romanticSection.innerHTML = '';
  if (sadSection) sadSection.innerHTML = '';
  if (partySection) partySection.innerHTML = '';

  // Fetch history and homepage categories concurrently
  const [historyData, data] = await Promise.all([
    api.get('/api/music/history?limit=24').catch(() => []),
    api.get('/api/music/home')
  ]);
  
  if (!data) return;

  // 1. Prepend Recently Played if user has history
  if (historyData && historyData.length && recentlyPlayedSection) {
    const seenIds = new Set();
    const recentTracks = [];
    historyData.forEach(item => {
      if (!seenIds.has(item.track_id)) {
        seenIds.add(item.track_id);
        recentTracks.push({
          id: item.track_id,
          title: item.track_title,
          artist: item.track_artist,
          album: item.track_album,
          album_art: item.track_album_art,
          stream_url: item.track_stream_url,
          source: 'jiosaavn'
        });
      }
    });

    if (recentTracks.length > 0) {
      const displayTracks = recentTracks.slice(0, 12);
      
      const secEl = document.createElement('section');
      secEl.className = 'dash-section';
      
      const titleEl = document.createElement('h2');
      titleEl.className = 'section-title';
      titleEl.textContent = 'Recently Played';
      secEl.appendChild(titleEl);
      
      const gridEl = document.createElement('div');
      gridEl.className = 'tracks-grid';
      secEl.appendChild(gridEl);
      
      recentlyPlayedSection.appendChild(secEl);
      renderTracksInGrid(displayTracks, gridEl, true);
    }
  }
  
  // 2. Load the other sections
  data.forEach(section => {
    let targetContainer = null;
    let secTitle = section.title;
    
    if (section.title.includes('Trending')) {
      targetContainer = trendingSection;
    } else if (section.title.includes('Romantic')) {
      targetContainer = romanticSection;
    } else if (section.title.includes('Sad')) {
      targetContainer = sadSection;
    } else if (section.title.includes('Party')) {
      targetContainer = partySection;
    } else if (section.title.includes('For You')) {
      targetContainer = forYouSection;
    }
    
    if (targetContainer) {
      const secEl = document.createElement('section');
      secEl.className = 'dash-section';
      
      const titleEl = document.createElement('h2');
      titleEl.className = 'section-title';
      titleEl.textContent = secTitle;
      secEl.appendChild(titleEl);
      
      const gridEl = document.createElement('div');
      gridEl.className = 'tracks-grid';
      secEl.appendChild(gridEl);
      
      targetContainer.appendChild(secEl);
      renderTracksInGrid(section.tracks || [], gridEl);
    }
  });
}

function renderTracksInGrid(tracks, gridEl, isHistory = false) {
  gridEl.innerHTML = '';
  if (!tracks.length) {
    gridEl.innerHTML = '<p class="empty-hint">No tracks found</p>';
    return;
  }
  tracks.forEach((t, i) => {
    const card = document.createElement('div');
    card.className = 'track-card suggested-card';
    card.style.animationDelay = `${i*0.04}s`;
    card.innerHTML = `
      <div style="position:relative; width:100%; aspect-ratio:1; overflow:hidden; border-radius:var(--radius);">
        <img class="track-card-art" src="${escapeHtml(t.album_art||'')}" alt="${escapeHtml(t.title)}" loading="lazy" onerror="this.style.background='linear-gradient(135deg,#1a1a3e,#0a0a14)'" />
        <div class="track-card-overlay">
          ${isHistory ? `<button class="overlay-remove-history-btn" title="Remove from History">&times;</button>` : ''}
          <div class="overlay-play-btn" title="Play"><svg viewBox="0 0 24 24" fill="currentColor" style="width:20px; height:20px; display:block;"><polygon points="5 3 19 12 5 21 5 3"/></svg></div>
          <div class="overlay-details">
            <span class="overlay-title">${escapeHtml(t.title)}</span>
            <span class="overlay-artist">${escapeHtml(t.artist)}</span>
          </div>
          <button class="overlay-queue-btn" title="Add to Queue">+</button>
        </div>
      </div>
      <div class="track-card-info">
        <span class="track-card-title">${escapeHtml(t.title)}</span>
        <span class="track-card-artist">${escapeHtml(t.artist)}</span>
      </div>
      <div class="track-card-actions">
        <button class="btn btn-primary btn-sm play-btn" style="display: flex; align-items: center; justify-content: center; gap: 4px;"><svg viewBox="0 0 24 24" fill="currentColor" style="width:12px; height:12px; display:inline-block;"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play</button>
        <button class="btn btn-ghost btn-sm queue-btn">+ Queue</button>
      </div>`;
    card.querySelector('.play-btn').addEventListener('click', e => { e.stopPropagation(); playTrack(t); });
    card.querySelector('.queue-btn').addEventListener('click', e => { e.stopPropagation(); addToQueue(t); });
    card.querySelector('.overlay-play-btn').addEventListener('click', e => { e.stopPropagation(); playTrack(t); });
    card.querySelector('.overlay-queue-btn').addEventListener('click', e => { e.stopPropagation(); addToQueue(t); });
    if (isHistory) {
      const removeBtn = card.querySelector('.overlay-remove-history-btn');
      if (removeBtn) {
        removeBtn.addEventListener('click', async e => {
          e.stopPropagation();
          try {
            await api.delete(`/api/music/history/${t.id}`);
            card.style.transform = 'scale(0.8)';
            card.style.opacity = '0';
            setTimeout(() => {
              card.remove();
              if (!gridEl.children.length) {
                gridEl.innerHTML = '<p class="empty-hint">Your listening history is empty.</p>';
              }
            }, 300);
            showToast('Removed from recently listened songs', 'success');
          } catch (err) {
            showToast('Error removing track from history', 'error');
          }
        });
      }
    }
    card.addEventListener('click', () => playTrack(t));
    gridEl.appendChild(card);
  });
}

// Profile panel pages and subtabs
function setupProfileTabs() {
  $$('.profile-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.profile-tab').forEach(t => t.classList.remove('active'));
      $$('.profile-tab-panel').forEach(p => p.classList.remove('active'));
      
      tab.classList.add('active');
      const targetPanel = $(`#profile-${tab.dataset.tab}-tab`);
      if (targetPanel) targetPanel.classList.add('active');
      
      if (tab.dataset.tab === 'playlists') loadPlaylistsProfile();
      else if (tab.dataset.tab === 'liked') loadLikedSongsProfile();
      else if (tab.dataset.tab === 'history') loadHistoryProfile();
    });
  });
}

async function loadPlaylistsProfile() {
  const listEl = $('#playlists-list');
  if (!listEl) return;
  listEl.innerHTML = '<p class="empty-hint">Loading playlists...</p>';
  
  const playlists = await api.get('/api/playlists');
  if (!playlists) return;
  
  listEl.innerHTML = '';
  if (!playlists.length) {
    listEl.innerHTML = '<p class="empty-hint">You haven\'t created any playlists yet.</p>';
    return;
  }
  
  playlists.forEach(pl => {
    const card = document.createElement('div');
    card.className = 'playlist-card';
    card.style.background = 'var(--bg-card)';
    card.style.padding = '16px';
    card.style.borderRadius = 'var(--radius-sm)';
    card.style.position = 'relative';
    card.style.display = 'flex';
    card.style.flexDirection = 'column';
    card.style.gap = '8px';
    
    let tracks = [];
    try { tracks = JSON.parse(pl.tracks || '[]'); } catch (e) { tracks = []; }
    
    card.innerHTML = `
      <h3 style="font-size: 1.1rem; font-weight: 600; margin: 0; display: flex; align-items: center; gap: 6px;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="btn-svg" style="margin-right:0;"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>${escapeHtml(pl.name)}</h3>
      <span style="font-size: 0.85rem; color: var(--text-3);">${tracks.length} songs</span>
      <div class="playlist-card-actions" style="margin-top: 12px; display: flex; gap: 8px;">
        <button class="btn btn-primary btn-sm play-pl-btn" ${tracks.length === 0 ? 'disabled' : ''} style="display: flex; align-items: center; justify-content: center; gap: 4px;"><svg viewBox="0 0 24 24" fill="currentColor" style="width:12px; height:12px; display:inline-block;"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play</button>
        <button class="btn btn-ghost btn-sm delete-pl-btn" style="display: flex; align-items: center; justify-content: center; gap: 4px;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:12px; height:12px; display:inline-block;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg> Delete</button>
      </div>
    `;
    
    card.querySelector('.play-pl-btn').addEventListener('click', () => {
      if (tracks.length > 0) {
        state.queue = [...tracks];
        const first = state.queue.shift();
        playTrack(first);
        renderQueue();
        showToast(`Playing playlist "${pl.name}"`, "success");
      }
    });
    
    card.querySelector('.delete-pl-btn').addEventListener('click', async () => {
      if (confirm(`Are you sure you want to delete playlist "${pl.name}"?`)) {
        const res = await api('DELETE', `/api/playlists/${pl.id}`);
        if (res) {
          showToast(`Deleted playlist "${pl.name}"`, "success");
          loadPlaylistsProfile();
        }
      }
    });
    
    listEl.appendChild(card);
  });
}

async function loadLikedSongsProfile() {
  const listEl = $('#profile-liked-songs-list');
  if (!listEl) return;
  listEl.innerHTML = '<p class="empty-hint">Loading liked songs...</p>';
  
  const liked = await api.get('/api/music/liked');
  if (!liked) return;
  
  listEl.innerHTML = '';
  if (!liked.length) {
    listEl.innerHTML = '<p class="empty-hint">No liked songs yet.</p>';
    return;
  }
  
  state.likedSongs = new Set(liked.map(s => s.track_id));
  
  const tracks = liked.map(s => ({
    id: s.track_id,
    title: s.track_title,
    artist: s.track_artist,
    album: s.track_album,
    album_art: s.track_album_art,
    stream_url: s.track_stream_url,
    source: 'jiosaavn'
  }));
  
  renderTracksInGrid(tracks, listEl);
}

async function loadHistoryProfile() {
  const listEl = $('#profile-history-list');
  if (!listEl) return;
  listEl.innerHTML = '<p class="empty-hint">Loading history...</p>';
  
  const history = await api.get('/api/music/history');
  if (!history) return;
  
  listEl.innerHTML = '';
  if (!history.length) {
    listEl.innerHTML = '<p class="empty-hint">Your listening history is empty.</p>';
    return;
  }
  
  const tracks = history.map(s => ({
    id: s.track_id,
    title: s.track_title,
    artist: s.track_artist,
    album: s.track_album,
    album_art: s.track_album_art,
    stream_url: s.track_stream_url,
    source: 'jiosaavn'
  }));
  
  renderTracksInGrid(tracks, listEl, true);
}

async function fetchUserLikedSongsList() {
  if (!state.token) return;
  const liked = await api.get('/api/music/liked');
  if (liked) {
    state.likedSongs = new Set(liked.map(s => s.track_id));
  }
}

async function logHistoryToBackend(track) {
  if (!state.token || !track) return;
  await api.post('/api/music/history', {
    track_id: track.id,
    track_title: track.title,
    track_artist: track.artist,
    track_album: track.album || "",
    track_album_art: track.album_art || "",
    track_stream_url: track.stream_url || ""
  });
}

