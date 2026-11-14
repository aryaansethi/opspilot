# Database Failover Runbook

Applies to the shared PostgreSQL cluster used by orders-api, inventory-service and catalog-service.

## Read-only transaction errors

`ERROR: cannot execute UPDATE in a read-only transaction` means the application is writing to a replica. This happens after a failover when connection pools still hold connections to the old primary, which has been demoted to a replica. Restart the application tasks or recycle the pools so new connections resolve the primary endpoint again.

## Connection storm after failover

When the primary changes, every service reconnects at once. Pools that open all connections immediately can exhaust `max_connections` and produce `FATAL: remaining connection slots are reserved for non-replication superuser connections`. Set `minimumIdle` low and add jitter to reconnect attempts.

## Disk full on the primary

`could not extend file` and `No space left on device` mean the primary volume is full. Writes fail but reads continue. Free space by removing old WAL archives only after checking replication slots; inactive replication slots are the usual cause of WAL growth.

## Lock timeouts during migrations

Migrations that take an `ACCESS EXCLUSIVE` lock block every query on the table. Set `lock_timeout = '5s'` in migration sessions so a blocked migration fails fast instead of queuing all traffic behind it.
