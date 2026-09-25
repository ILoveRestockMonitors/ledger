/* Short-lived dashboard reads, shared between scopes and concurrent requests. */
(function (host) {
  'use strict';
  function createCache(request, now = Date.now, ttl = 15000) {
    const entries = new Map();
    return {
      clear() { entries.clear(); },
      read(path) {
        const cached = entries.get(path);
        if (cached && (cached.pending || now() - cached.at < ttl)) return cached.promise;
        const entry = { pending: true, at: now() };
        entry.promise = Promise.resolve().then(() => request(path)).then(value => {
          entry.pending = false; entry.at = now(); return value;
        }, error => {
          if (entries.get(path) === entry) entries.delete(path);
          throw error;
        });
        entries.set(path, entry);
        return entry.promise;
      }
    };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = createCache;
  else host.LedgerHomeCache = createCache(path => api(path));
})(typeof window === 'undefined' ? globalThis : window);
