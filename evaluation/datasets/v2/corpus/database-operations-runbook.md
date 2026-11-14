# Database Operations Runbook

## Connection limits

The shared PostgreSQL cluster allows 400 connections in total. Each service's connection pool size multiplied by its task count must fit inside its allocation: orders-api has 200, inventory-service 120, catalog-service 80.

## Finding long-running queries

Query `pg_stat_activity` for rows where `state = 'active'` and `now() - query_start > interval '30 seconds'`. Terminate a runaway query with `pg_terminate_backend(pid)` only after confirming it is not a migration.

## Replica lag

Read replicas lag behind during large batch writes. Alert when replica lag exceeds 30 seconds; reads that need fresh data must go to the primary.
