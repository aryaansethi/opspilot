# INC-2026-044: Notifications worker crash loop after secrets migration

Date: 2026-10-21. Severity: SEV-2. Duration: 25 minutes.

## Summary

notifications-worker tasks crashed on start-up and restarted continuously. No emails were sent for 25 minutes.

## Root cause

During the migration of configuration to Secrets Manager, the `SMTP_FROM_ADDRESS` variable was left out of the new task definition. The worker exited with `KeyError: 'SMTP_FROM_ADDRESS'`.

## Resolution

The variable was added back to the task definition and the service was redeployed.

## Follow-up actions

- Validate required environment variables in the deploy pipeline before rollout.
