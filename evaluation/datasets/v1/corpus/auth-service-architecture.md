# Auth Service Architecture

## Overview

auth-service issues JWT access tokens (15 minute lifetime) and refresh tokens (30 days). Every other service validates tokens locally using the public keys from the JWKS endpoint.

## Storage

User credentials live in the `auth-db` PostgreSQL database. Sessions and refresh tokens are stored hashed.

## Dependencies

auth-service depends on `auth-db` and on the notifications-worker for password reset emails. It has no dependency on orders-api or payments-api.
