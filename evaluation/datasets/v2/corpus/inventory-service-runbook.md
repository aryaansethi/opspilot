# Inventory Service Runbook

Service: inventory-service. Owner: Fulfilment team.

## Stock reservation deadlocks

Deadlocks show up as `SQLSTATE 40P01` errors when two orders reserve the same SKUs in a different order. The service retries once; persistent deadlocks mean the lock ordering fix (sort SKUs before locking) is missing.

## Consumer lag on inventory-events

inventory-service consumes the `inventory-events` Kafka topic. Alert when consumer lag exceeds 50000 messages. Lag usually follows a slow database, not a Kafka problem.

## Nightly reconciliation job

The reconciliation job runs at 02:00 UTC and compares stock with the warehouse system. It runs as a separate ECS task with 2 GB of memory.
