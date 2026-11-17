/* Service Worker — 台南市開放資料瀏覽器
 * 策略:
 *  - 頁面導覽:網路優先,離線時顯示 /offline
 *  - 靜態資源(/assets、/static、/pwa):stale-while-revalidate
 *  - API、WebSocket/SSE、非 GET 請求:一律不攔截(資料需即時連線)
 * 更新程式後,把 VERSION 加 1 即可讓舊快取失效。
 */
const VERSION = "v1";
const CACHE = `tainan-static-${VERSION}`;

const PRECACHE = [
  "/offline",
  "/manifest.webmanifest",
  "/pwa/icons/icon-192.png",
  "/pwa/icons/icon-512.png",
];

const CACHEABLE_PREFIXES = ["/assets/", "/static/", "/pwa/", "/_app/"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k.startsWith("tainan-") && k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // 頁面導覽
  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match("/offline")));
    return;
  }

  // 靜態資源
  if (CACHEABLE_PREFIXES.some((p) => url.pathname.startsWith(p))) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        const network = fetch(req)
          .then((res) => {
            if (res && res.ok) cache.put(req, res.clone());
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
