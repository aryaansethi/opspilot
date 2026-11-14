# Latency Troubleshooting Guide

## p95 versus p50

If p50 latency is stable but p95 rises, a subset of requests is slow: look for one slow dependency, lock contention, or a specific endpoint. If p50 rises too, the whole service is saturated (CPU, connection pool or thread pool).

## N+1 queries

A request that issues one query per item in a list (N+1 queries) gets slower as data grows. Look for the same SQL statement repeated hundreds of times per request in traces, and replace it with a single batched query.

## Thread pool exhaustion

`RejectedExecutionException` means the request thread pool is full and new work is rejected. It often follows a slow downstream call that holds threads; add a timeout to that call before increasing the pool size.

## Cold caches after a deployment

New tasks start with empty in-memory caches, so latency is higher for the first minutes after a deploy. Warm critical caches at start-up or deploy gradually so old tasks keep serving.

## DNS resolution delays

Intermittent extra latency of about 5 seconds on outbound calls usually means DNS lookups are timing out and retrying. Check the resolver configuration and enable DNS caching in the client.
