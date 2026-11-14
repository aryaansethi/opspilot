# INC-2026-052: Search latency spike after every deployment

Date: 2026-10-30. Severity: SEV-3.

## Summary

search-api p95 latency rose from 300 ms to 1.8 s for about 10 minutes after each deployment, then recovered on its own.

## Root cause

All tasks were replaced at once, and each new task started with an empty in-memory cache of category facets, so every request went to OpenSearch until the caches filled.

## Resolution

Deployments now replace 25 percent of tasks at a time, and the facet cache is warmed at start-up.
