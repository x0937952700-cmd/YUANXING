const VERSION = "v20260418"; // 🔥 每次改這個即可

self.addEventListener("install", event => {
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});

// ❗ 完全不快取 HTML
self.addEventListener("fetch", event => {
  const req = event.request;

  // HTML → 永遠走網路
  if (req.headers.get("accept")?.includes("text/html")) {
    event.respondWith(fetch(req, { cache: "no-store" }));
    return;
  }

  // 其他 → 直接走網路（不快取）
  event.respondWith(fetch(req));
});