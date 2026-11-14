# INC-2026-022: Logins rejected after signing key rotation

Date: 2026-04-02. Severity: SEV-2. Duration: 55 minutes.

## Summary

Users were logged out and API calls failed with `AUTH_INVALID_KID` for almost an hour.

## Root cause

The new signing key was published to the JWKS endpoint and used for signing at the same moment. Downstream services cache JWKS for 1 hour and rejected tokens signed with the unknown key.

## Resolution

Signing was switched back to the previous key and every service's JWKS cache was refreshed.

## Follow-up actions

- Publish new keys at least 2 hours before using them.
- Add the `POST /internal/jwks/refresh` endpoint to every service.
