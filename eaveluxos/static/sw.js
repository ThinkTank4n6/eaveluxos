/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   EaveLuxOS on a phone's home screen (4.14): the app's own files are kept
   on the phone, so it opens at once, and says plainly when the app computer
   can't be reached (away from home Wi-Fi, or the computer is off).

   Only the app's files are kept: never anything from /api/ (the lights,
   settings, accounts), which always comes fresh from the app computer.
   Each version keeps its own set; a new version replaces the old one.
   Service workers run only on https:// addresses and on this computer
   (localhost); on a plain http:// address the app works as before. */
'use strict';
const VERSION = '__VERSION__';
const CACHE = 'eaveluxos-' + VERSION;
const FILES = ['./', 'index.html', 'app.css', 'app.js', 'theme.js', 'markdown.js', 'roofline.js', 'painter.js', 'whites.js',
  'housefx.js', 'calib.js', 'mood.js', 'bands.js', 'beat.js', 'musiczones.js', 'qr.js', 'colors.js', 'nav.js', 'search.js', 'merge.js',
  'zonemix.js', 'security.js', 'offline.html', 'manifest.webmanifest', 'icon.svg', 'logo-mark.svg', 'icon-180.png', 'icon-192.png',
  'icon-512.png', 'icon-maskable-192.png', 'icon-maskable-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES.map(f => new Request(f, { cache: 'reload' })))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('eaveluxos-') && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.includes('/api/')) return;                // the lights and settings: always live, never kept
  if (req.mode === 'navigate') {
    // The page: fresh when the app computer answers; otherwise the kept copy,
    // which then says the app computer can't be reached.
    e.respondWith(fetch(req).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put('index.html', copy)); }
      return r;
    }).catch(() => caches.match('index.html').then(r => r || caches.match('offline.html'))));
    return;
  }
  // The app's files: fresh from the app computer (a home network is quick),
  // and the kept copy only when it can't be reached. Review #2: a kept copy
  // first meant the first visit after an update ran the old files with the
  // new page.
  e.respondWith(caches.open(CACHE).then(c => {
    const kept = () => c.match(req, { ignoreSearch: true }).then(hit => hit || Promise.reject(new Error('offline')));
    const fresh = new Promise((ok, no) => {
      const t = setTimeout(() => kept().then(ok, () => {}), 4000);       // a slow network: the kept copy, if there is one
      fetch(req).then(r => { clearTimeout(t); if (r.ok && r.type === 'basic') c.put(req, r.clone()); ok(r); })
        .catch(() => { clearTimeout(t); kept().then(ok, no); });
    });
    return fresh;
  }));
});
