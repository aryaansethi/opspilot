# Release notes: orders-api 4.3

Release date: 2026-11-12. Deployed by the Commerce Platform team.

## Changes

- New endpoint `GET /orders/{id}/timeline`.
- Upgraded the PostgreSQL JDBC driver to 42.7.
- Configuration: `spring.datasource.hikari.maximum-pool-size` changed from 50 to 10 to reduce load on the shared database.

## Known risks

The smaller connection pool has not been load tested at peak checkout traffic.
