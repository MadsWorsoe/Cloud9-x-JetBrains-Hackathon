const cache = new Map();

// URLs that we want to persist across page refreshes
const PERSISTENT_URLS = [
  "/api/champions/",
  "/api/teams/",
];

export async function fetchWithCache(url, options = {}) {
  const isGET = !options.method || options.method === "GET";
  const cacheKey = JSON.stringify({ url, options });
  
  // 1. Check in-memory cache (only for GET requests)
  if (isGET && cache.has(cacheKey)) {
    return cache.get(cacheKey);
  }

  // 2. Check localStorage for persistent URLs (only for GET requests)
  const shouldPersist = PERSISTENT_URLS.includes(url) && isGET;

  if (shouldPersist) {
    const stored = localStorage.getItem(`api_cache_${url}`);
    if (stored) {
      try {
        const data = JSON.parse(stored);
        cache.set(cacheKey, data);
        
        // Background refresh to keep data up to date for next visit
        fetch(url, options)
          .then((r) => r.json())
          .then((freshData) => {
            localStorage.setItem(`api_cache_${url}`, JSON.stringify(freshData));
            cache.set(cacheKey, freshData);
          })
          .catch(() => {});
          
        return data;
      } catch (e) {
        localStorage.removeItem(`api_cache_${url}`);
      }
    }
  }

  // 3. Fetch from network
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  const data = await response.json();
  cache.set(cacheKey, data);

  if (shouldPersist) {
    localStorage.setItem(`api_cache_${url}`, JSON.stringify(data));
  }

  return data;
}

export function clearCache() {
  cache.clear();
  PERSISTENT_URLS.forEach(url => localStorage.removeItem(`api_cache_${url}`));
}
