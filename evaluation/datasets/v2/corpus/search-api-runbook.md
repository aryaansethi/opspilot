# Search API Runbook

Service: search-api. Owner: Discovery team.

## Cluster health yellow or red

search-api queries an OpenSearch cluster with 3 data nodes. Yellow means replica shards are unassigned; red means at least one primary shard is unassigned and some searches fail.
The most common cause of red health is the disk flood-stage watermark (95 percent), which makes indices read-only.

## Slow queries

Queries slower than 2 seconds are logged to the slow log. Wildcard queries with a leading `*` are the usual cause; reject them at the API layer.

## Circuit breaker exceptions

`CircuitBreakingException` means a request would exceed the JVM memory limit for field data or aggregations. Reduce aggregation size or add memory to data nodes.

## Reindexing

Reindex the product index with the `reindex-products` job. It takes about 40 minutes and uses an alias swap, so search stays available.
