# INC-2026-047: Write errors and connection storm after database failover

Date: 2026-10-02. Severity: SEV-1. Duration: 34 minutes.

## Summary

After an unplanned failover of the shared PostgreSQL cluster, orders-api returned errors for 34 minutes. Logs showed `cannot execute UPDATE in a read-only transaction` followed by `remaining connection slots are reserved`.

## Root cause

orders-api pools kept connections to the old primary, which had become a read-only replica. When tasks were restarted, all services reconnected at the same time and exhausted the 400 connection limit.

## Resolution

Services were restarted in sequence, starting with orders-api, so connections stayed below the limit.

## Follow-up actions

- Recycle connection pools automatically when a read-only transaction error is seen.
- Add jitter to reconnect attempts and lower `minimumIdle`.
