const CACHE_NAME = 'vynce-audio-cache-v1';
const MAX_AUDIO_KEYS = 20;

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(clients.claim());
});

// Helper to clean up old audio entries in cache if we exceed MAX_AUDIO_KEYS
async function limitCacheSize(cache, maxItems) {
  const keys = await cache.keys();
  if (keys.length > maxItems) {
    for (let i = 0; i < keys.length - maxItems; i++) {
      await cache.delete(keys[i]);
    }
  }
}

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  const isAudio = request.destination === 'audio' || url.pathname.includes('/stream') || url.hostname.includes('jiosaavn') || request.url.includes('.mp3');

  if (request.method !== 'GET' || !isAudio) {
    return;
  }

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      const cachedResponse = await cache.match(request.url);

      if (cachedResponse) {
        if (request.headers.has('range')) {
          return returnRangeResponse(request, cachedResponse.clone());
        }
        return cachedResponse;
      }

      try {
        const response = await fetch(request);
        
        if (response.status === 200 || response.status === 206) {
          if (response.status === 206) {
            fetchFullAndCache(request.url, cache);
          } else {
            await cache.put(request.url, response.clone());
            await limitCacheSize(cache, MAX_AUDIO_KEYS);
          }
        }
        return response;
      } catch (err) {
        return new Response('Offline audio fallback', { status: 408 });
      }
    })()
  );
});

async function fetchFullAndCache(url, cache) {
  try {
    const response = await fetch(url, { headers: { 'range': 'bytes=0-' } });
    if (response.status === 200 || response.status === 206) {
      await cache.put(url, response);
      await limitCacheSize(cache, MAX_AUDIO_KEYS);
    }
  } catch (e) {
    console.error('[SW] Failed to prefetch full audio for cache:', e);
  }
}

async function returnRangeResponse(request, response) {
  const rangeHeader = request.headers.get('range');
  const buffer = await response.arrayBuffer();
  
  const match = rangeHeader.match(/^bytes=(\d+)-(\d+)?$/);
  if (!match) {
    return new Response(buffer, {
      status: 200,
      headers: response.headers
    });
  }

  const start = parseInt(match[1], 10);
  const end = match[2] ? parseInt(match[2], 10) : buffer.byteLength - 1;
  const chunk = buffer.slice(start, end + 1);

  const headers = new Headers(response.headers);
  headers.set('Content-Range', `bytes ${start}-${end}/${buffer.byteLength}`);
  headers.set('Content-Length', chunk.byteLength);

  return new Response(chunk, {
    status: 206,
    statusText: 'Partial Content',
    headers: headers
  });
}
