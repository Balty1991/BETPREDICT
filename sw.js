// BETPREDICT Service Worker — auto-update on deploy
const VERSION = 'bp-20260527-235959';
const CACHE = `betpredict-${VERSION}`;

// App shell — fișiere statice cache-uite
const SHELL = [
  './',
  './index.html',
  './assets/modern.css',
  './assets/betpredict_20.css',
  './assets/betpredict_20.js',
  './assets/betpredict_upgrade.css',
  './assets/betpredict_upgrade.js',
  './assets/shared-utils.js',
  './assets/sanitize.js',
  './manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL.map(u => new Request(u, { cache: 'reload' }))))
      .then(() => self.skipWaiting()) // activare imediată, fără așteptare
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    // Șterge toate cache-urile vechi
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim()) // preia controlul tuturor tab-urilor deschise
      .then(() => {
        // Trimite mesaj la toate tab-urile: "versiune nouă, reîncarcă"
        return self.clients.matchAll({ type: 'window' });
      })
      .then(clients => clients.forEach(c => c.postMessage({ type: 'SW_UPDATED', version: VERSION })))
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // HTML principal — întotdeauna din rețea (niciodată cache vechi)
  if (url.pathname.endsWith('/') || url.pathname.endsWith('.html')) {
    event.respondWith(
      fetch(req, { cache: 'no-store' })
        .then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(req, res.clone()));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Fișiere JSON din /data/ — întotdeauna din rețea (date proaspete), fallback cache
  if (url.pathname.includes('/data/')) {
    event.respondWith(
      fetch(req, { cache: 'no-store' })
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(req, clone));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // CSS/JS assets — cache first, update în background
  event.respondWith(
    caches.match(req).then(cached => {
      const networkUpdate = fetch(req, { cache: 'no-store' })
        .then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(req, res.clone()));
          return res;
        })
        .catch(() => cached);
      return cached || networkUpdate;
    })
  );
});
