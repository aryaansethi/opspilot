# Application Error Codes Reference

Error codes appear in logs as `code=<CODE>` and in API error responses.

## Orders and inventory

- `ERR_POOL_TIMEOUT`: orders-api could not get a database connection from its pool within 30 seconds.
- `INV_RESERVATION_CONFLICT`: inventory-service could not reserve stock because another order holds the same SKU; the client should retry once.

## Payments

- `PAY_GATEWAY_502`: the card gateway returned a bad gateway response.
- `IDEMP_409`: an idempotency key was reused with a different request body.

## Identity

- `AUTH_INVALID_KID`: a token was signed with an unknown key ID.
- `AUTH_TOKEN_EXPIRED`: the access token is older than its 15 minute lifetime; the client should refresh it.

## Search and notifications

- `SRCH_QUERY_TOO_BROAD`: search-api rejected a query that starts with a wildcard.
- `NOTIF_TEMPLATE_MISSING_VAR`: notifications-worker could not render a template because a variable was missing; the message goes to the DLQ.
