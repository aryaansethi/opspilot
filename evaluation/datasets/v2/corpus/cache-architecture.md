# Catalog Cache Architecture

The catalog-service caches product data in Redis (ElastiCache, cache.r7g.large) with a 15 minute TTL.

## Eviction behaviour

Redis uses the `allkeys-lru` eviction policy. When memory usage reaches maxmemory, the least recently used keys are evicted and the cache hit ratio falls. A hit ratio below 80 percent increases load on the catalog database.

## Cache stampede protection

catalog-service uses request coalescing so that only one request rebuilds an expired key.
