# Orders API Runbook

Service: orders-api. Owner: Commerce Platform team. Environment: production runs in us-east-1 on ECS.

## Elevated latency after a deployment

1. Compare p95 latency on the `orders-api` dashboard for 30 minutes before and after the deploy.
2. Check for `HikariPool-1 - Connection is not available, request timed out after 30000ms` in the `/ecs/orders-api` log group.
3. Compare `spring.datasource.hikari.maximum-pool-size` between the current and previous release. The expected value is 50.
4. If the pool size changed, roll back the configuration first and confirm latency returns to baseline before investigating further.

## Database connection exhaustion

Symptoms: rising p95 latency, HTTP 500 responses, and the error code `ERR_POOL_TIMEOUT` in application logs.

Check active connections with the `hikaricp.connections.active` metric. If active connections equal the maximum pool size for more than 5 minutes, the pool is exhausted.

Common causes:
- Pool size reduced in configuration.
- Slow queries holding connections (check `pg_stat_activity`).
- Connection leaks after a code change.

## Rollback procedure

Use the `deploy-orders` pipeline and choose "Roll back to previous task definition". Rollbacks take about 6 minutes.
