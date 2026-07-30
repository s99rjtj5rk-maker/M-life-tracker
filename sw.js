const CACHE='m-life-v4';
const ASSETS=['/','/index.html','/manifest.json','/app-icon.png','/app-icon-512.png','/apple-touch-icon.png','/capybara.png'];
self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).catch(()=>{}));
  self.skipWaiting();
});
self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.map(k=>caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch',e=>{
  // 图标和manifest不缓存，始终从网络获取最新
  if(e.request.url.match(/\.(png|json|ico)/)){
    e.respondWith(fetch(e.request));
    return;
  }
  e.respondWith(
    caches.match(e.request).then(cached=>cached||fetch(e.request))
  );
});
