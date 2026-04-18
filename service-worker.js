const CACHE_NAME = "static-v1";

// 👉 只快取靜態資源（不要放HTML）
const STATIC_ASSETS = [
  "/static/app.js",
  "/static/style.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

// 安裝
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// 啟用
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

// 🔥 核心：Fetch策略
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);

  // ❗ HTML 一律走網路（永遠最新）
  if (event.request.headers.get("accept").includes("text/html")) {
    event.respondWith(fetch(event.request));
    return;
  }

  // 靜態資源 → cache優先
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        return cached || fetch(event.request);
      })
    );
  }
});