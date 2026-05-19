/* ═══════════════════════════════════════════════════════════════
   JamSync v2 — Main SPA Logic
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
};

/* ═══════ AUDIO ═══════ */
const audio = new Audio();
audio.crossOrigin = 'anonymous';
audio.preload = 'auto';
const savedVol = localStorage.getItem('jamsync_volume');
if (savedVol !== null) state.volume = parseFloat(savedVol);
audio.volume = state.volume;

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
      const e = await res.json().catch(()=>({detail:res.statusText}));
      let msg = 'Request failed';
      if (e && e.detail) {
        if (typeof e.detail === 'string') {
          msg = e.detail;
        } else if (Array.isArray(e.detail)) {
          msg = e.detail.map(err => {
            const field = err.loc ? err.loc[err.loc.length - 1] : '';
            return field ? `${field}: ${err.msg}` : err.msg;
          }).join(', ');
        }
      }
      throw new Error(msg);
    }
    if (res.status === 204) return null;
    return await res.json();
  } catch (e) { showToast(e.message || 'Network error', 'error'); console.error(`[API] ${method} ${path}`, e); return null; }
}
api.get = p => api('GET', p);
api.post = (p, b) => api('POST', p, b);
api.put = (p, b) => api('PUT', p, b);

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
      loadRooms(); loadTrending();
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
    localStorage.setItem('jamsync_token', data.access_token);
    sessionStorage.removeItem('jamsync_token');
  } else {
    sessionStorage.setItem('jamsync_token', data.access_token);
    localStorage.removeItem('jamsync_token');
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
    localStorage.setItem('jamsync_token', data.access_token);
    sessionStorage.removeItem('jamsync_token');
  } else {
    sessionStorage.setItem('jamsync_token', data.access_token);
    localStorage.removeItem('jamsync_token');
  }
  
  hideAuthModal();
  showToast('Welcome to JamSync! 🎵', 'success');
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
  localStorage.removeItem('jamsync_token');
  sessionStorage.removeItem('jamsync_token');
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
      <div class="room-card-listeners">👥 ${r.listener_count ?? 0} listening</div>
      <div class="room-card-track">${r.current_track ? `♫ ${escapeHtml(r.current_track.title)}` : 'No track playing'}</div>
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
  ws.onopen = () => { wsRetries = 0; startHeartbeat(); showToast('Connected!', 'success'); };
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
      if (d.queue) { state.queue = d.queue; renderQueue(); }
      if (d.users) renderListeners(d.users);
      updatePlaybackUI(); break;
    case 'user_joined': showToast(`${escapeHtml(d.username)} joined`, 'info'); updateLC(d.listener_count); break;
    case 'user_left': showToast(`${escapeHtml(d.username)} left`, 'info'); updateLC(d.listener_count); break;
    case 'play_track': loadTrack(d.track, 0); audio.play().catch(()=>{}); state.isPlaying = true; updatePlaybackUI(); break;
    case 'sync': handleSync(d); break;
    case 'pause': audio.pause(); state.isPlaying = false; updatePlaybackUI(); break;
    case 'resume': audio.play().catch(()=>{}); state.isPlaying = true; updatePlaybackUI(); break;
    case 'seek': audio.currentTime = d.position; break;
    case 'queue_update': state.queue = d.queue || []; renderQueue(); break;
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
function loadTrack(track, startAt = 0) {
  if (!track?.stream_url) return;
  state.currentTrack = track;
  try { audio.src = track.stream_url; audio.currentTime = startAt; } catch(e) { showToast('Could not load track', 'error'); return; }
  const t = $('#player-track-title'); if(t) t.textContent = track.title || 'Unknown';
  const a = $('#player-track-artist'); if(a) a.textContent = track.artist || 'Unknown';
  const d = $('#time-total'); if(d) d.textContent = formatTime(track.duration);
  const img = $('#player-album-art');
  if(img) { img.src = track.album_art || ''; img.alt = track.title || ''; }
  const bar = $('#progress-fill'); if(bar) bar.style.width = '0%';
  const cur = $('#time-current'); if(cur) cur.textContent = '0:00';
}

function togglePlay() {
  if(!audio.src) return;
  if(state.isPlaying) { audio.pause(); state.isPlaying = false; if(state.currentRoom) sendWS('pause'); }
  else { audio.play().catch(e => showToast('Click play again — browser blocked autoplay', 'info')); state.isPlaying = true; if(state.currentRoom) sendWS('resume'); }
  updatePlaybackUI();
}

function seekTo(pos) { if(!audio.src) return; audio.currentTime = pos; if(state.currentRoom) sendWS('seek', {position:pos}); }
function setVolume(v) { state.volume = Math.max(0,Math.min(1,v)); audio.volume = state.volume; localStorage.setItem('jamsync_volume', state.volume); updateVolumeUI(); }

async function playNext() {
  if(!state.queue.length) {
    if (state.currentTrack) {
      showToast('Autoplay: Finding next similar song...', 'info');
      try {
        const res = await api.get(`/api/music/song/${state.currentTrack.id}/similar?limit=5`);
        if (res && res.tracks && res.tracks.length) {
          const next = res.tracks[0];
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
    if (state.currentTrack && state.currentTrack.id !== next.id) {
      state.history.push(state.currentTrack);
      if (state.history.length > 50) state.history.shift();
    }
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

audio.addEventListener('timeupdate', () => {
  const dur = audio.duration || state.currentTrack?.duration || 0; if(!dur) return;
  const pct = (audio.currentTime/dur)*100;
  const bar = $('#progress-fill'); if(bar) bar.style.width = `${pct}%`;
  const thumb = $('#progress-thumb'); if(thumb) thumb.style.left = `${pct}%`;
  const cur = $('#time-current'); if(cur) cur.textContent = formatTime(audio.currentTime);
});
audio.addEventListener('ended', () => { state.isPlaying = false; updatePlaybackUI(); playNext(); });
audio.addEventListener('error', () => { showToast('Playback error — skipping', 'error'); playNext(); });

function updatePlaybackUI() {
  const btn = $('#btn-play-pause'); if(!btn) return;
  const play = btn.querySelector('.icon-play');
  const pause = btn.querySelector('.icon-pause');
  if(play) play.style.display = state.isPlaying ? 'none' : '';
  if(pause) pause.style.display = state.isPlaying ? '' : 'none';
}
function updateVolumeUI() {
  const s = $('#volume-slider'); if(s) s.value = Math.round(state.volume * 100);
}

function renderQueue() {
  const c = $('#queue-list'); if(!c) return;
  if(!state.queue.length) { c.innerHTML = '<p class="empty-hint">Queue is empty</p>'; return; }
  c.innerHTML = '';
  state.queue.forEach((t,i) => {
    const d = document.createElement('div'); d.className = 'queue-item';
    d.innerHTML = `
      <img class="queue-item-art" src="${escapeHtml(t.album_art||'')}" alt="" onerror="this.style.display='none'" />
      <div class="queue-item-info"><span class="queue-item-title">${escapeHtml(t.title)}</span><span class="queue-item-artist">${escapeHtml(t.artist)}</span></div>
      <span style="font-size:12px;color:var(--text-3)">${formatTime(t.duration)}</span>`;
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

async function loadTrending() {
  const data = await api.get('/api/music/trending?limit=20');
  if(!data) return;
  renderTrackCards(data.tracks || [], '#trending-tracks');
}

function renderTrackCards(tracks, sel) {
  const c = $(sel); if(!c) return;
  c.innerHTML = '';
  if(!tracks.length) { c.innerHTML = '<p class="empty-hint">No tracks found</p>'; return; }
  tracks.forEach((t, i) => {
    const card = document.createElement('div');
    card.className = 'track-card'; card.style.animationDelay = `${i*0.04}s`;
    card.innerHTML = `
      <div style="position:relative">
        <img class="track-card-art" src="${escapeHtml(t.album_art||'')}" alt="${escapeHtml(t.title)}" loading="lazy" onerror="this.style.background='linear-gradient(135deg,#1a1a3e,#0a0a14)'" />
        <div class="track-card-overlay">▶</div>
      </div>
      <div class="track-card-info">
        <span class="track-card-title">${escapeHtml(t.title)}</span>
        <span class="track-card-artist">${escapeHtml(t.artist)}</span>
      </div>
      <div class="track-card-actions">
        <button class="btn btn-primary btn-sm play-btn">▶ Play</button>
        <button class="btn btn-ghost btn-sm queue-btn">+ Queue</button>
      </div>`;
    card.querySelector('.play-btn').addEventListener('click', e => { e.stopPropagation(); playTrack(t); });
    card.querySelector('.queue-btn').addEventListener('click', e => { e.stopPropagation(); addToQueue(t); });
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
    if (state.currentTrack && state.currentTrack.id !== track.id) {
      state.history.push(state.currentTrack);
      if (state.history.length > 50) state.history.shift();
    }
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

  // Dashboard search
  const searchInput = $('#search-music-input');
  const debouncedDashSearch = debounce(async q => {
    if(q.length < 2) { $('#search-results-section').style.display = 'none'; return; }
    const tracks = await searchMusic(q);
    if(tracks && tracks.length) {
      $('#search-results-section').style.display = '';
      renderTrackCards(tracks, '#search-results');
    }
  }, 400);
  if(searchInput) {
    searchInput.addEventListener('input', e => debouncedDashSearch(e.target.value));
    searchInput.addEventListener('keydown', e => { if(e.key === 'Enter') { e.preventDefault(); debouncedDashSearch(searchInput.value); } });
  }

  // Genre chips
  $$('.genre-chip').forEach(chip => {
    chip.addEventListener('click', async () => {
      $$('.genre-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      const genre = chip.dataset.genre;
      const t = $('#genre-results-title'); if(t) t.textContent = `🎭 ${chip.textContent.trim()}`;
      const sec = $('#genre-results-section'); if(sec) sec.style.display = '';
      const c = $('#genre-results'); if(c) c.innerHTML = '<div class="track-skeleton"></div><div class="track-skeleton"></div>';
      const tracks = await searchMusic(genre);
      if(tracks) renderTrackCards(tracks, '#genre-results');
    });
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

  // Boot
  const savedToken = localStorage.getItem('jamsync_token') || sessionStorage.getItem('jamsync_token');
  if(savedToken) { state.token = savedToken; loadCurrentUser().then(handleRoute); }
  else handleRoute();

  updateVolumeUI(); updatePlaybackUI();
  console.log('[JamSync] v2 ready ✓');
});
