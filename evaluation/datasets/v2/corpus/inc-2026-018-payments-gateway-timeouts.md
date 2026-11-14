# INC-2026-018: Payment authorization timeouts

Date: 2026-02-20. Severity: SEV-1. Duration: 38 minutes.

## Summary

After payments-api 2.8 was deployed, 9 percent of card authorizations failed with timeouts during the evening peak.

## Root cause

Release 2.8 reduced the gateway call timeout from 8 seconds to 3 seconds. The gateway's p99 latency at peak is about 4.5 seconds, so slow but successful authorizations were cut off and retried.

## Resolution

The timeout was restored to 8 seconds with a configuration rollback.

## Follow-up actions

- Load test timeout changes against gateway p99 latency.
- Alert on authorization failure rate above 3 percent.
