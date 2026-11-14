# Auth Service Runbook

Service: auth-service. Owner: Identity team.

## Token validation errors

`AUTH_INVALID_KID` means a JWT was signed with a key ID that the validating service does not know. This usually happens right after signing key rotation, when downstream services still cache the old JWKS.
Downstream services cache the JWKS endpoint for 1 hour. Force a refresh by calling `POST /internal/jwks/refresh` on each service.

## Signing key rotation

Signing keys rotate every 30 days. Publish the new key to the JWKS endpoint at least 2 hours before it is used for signing, so every cache picks it up.

## Login latency spikes

Password hashing uses bcrypt with cost factor 12. Login latency above 800 ms usually means CPU saturation on auth-service tasks; scale out before lowering the cost factor.

## Account lockout

Accounts lock for 15 minutes after 10 failed logins. Support can unlock an account with the admin console; never disable lockout globally.
