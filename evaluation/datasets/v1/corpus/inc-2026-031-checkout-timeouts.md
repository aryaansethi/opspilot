# INC-2026-031: Checkout timeouts after release 4.2

Date: 2026-03-14. Severity: SEV-2. Duration: 47 minutes.

## Summary

After release 4.2 of orders-api, checkout requests timed out and p95 latency rose from 180 ms to 2.4 s. The error rate on POST /orders reached 12 percent.

## Timeline

- 14:02 UTC release 4.2 deployed.
- 14:09 UTC alarm `orders-api-p95-latency` fired.
- 14:21 UTC on-call found `ERR_POOL_TIMEOUT` errors and saw that maximum-pool-size had been changed from 50 to 10 in release 4.2.
- 14:49 UTC configuration rolled back; latency returned to baseline by 14:55 UTC.

## Root cause

A configuration change in release 4.2 reduced the database connection pool from 50 to 10 connections, which was too small for peak checkout traffic.

## Follow-up actions

- Add a config validation check for pool size in CI.
- Alert when `hikaricp.connections.pending` stays above 0 for 5 minutes.
