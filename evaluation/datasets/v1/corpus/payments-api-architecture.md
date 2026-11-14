# Payments API Architecture

## Overview

payments-api accepts payment intents from orders-api and authorizes cards through an external gateway. It runs on ECS with 4 tasks in production.

## Dependencies

- PostgreSQL database `payments-db` (db.r6g.large) stores payment intents and ledger entries.
- Redis stores idempotency keys for 24 hours.
- The external card gateway is called over HTTPS.

## Timeouts and retries

Calls to the card gateway use an 8 second timeout with 2 retries and exponential backoff with jitter. Retries are only allowed for requests that carry an idempotency key.

## Data retention

Card numbers are never stored; only the gateway token and the last four digits are kept. Ledger entries are retained for 7 years.
