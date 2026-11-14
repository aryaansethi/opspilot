# Platform Architecture Overview

## Services and owners

- orders-api: Commerce Platform team.
- payments-api: Payments team.
- catalog-service: Discovery team.
- search-api: Discovery team.
- auth-service: Identity team.
- inventory-service: Fulfilment team.
- notifications-worker: Growth Platform team.

## Request flow for checkout

The web app calls orders-api, which reserves stock in inventory-service and then calls payments-api to authorize the card. Confirmation emails are sent by notifications-worker.

## Service level objectives

- orders-api: p95 latency below 300 ms and 99.9 percent availability.
- payments-api: 99.95 percent availability.
- search-api: p95 latency below 500 ms.

## Shared database cluster

orders-api, inventory-service and catalog-service share one PostgreSQL cluster with `max_connections` set to 400.
