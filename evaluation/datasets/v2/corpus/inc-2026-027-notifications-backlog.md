# INC-2026-027: Password reset emails delayed by two hours

Date: 2026-05-18. Severity: SEV-3.

## Summary

A marketing campaign enqueued 1.2 million emails into `notifications-queue`. Password reset emails waited behind them for up to 2 hours.

## Root cause

All notification types shared one queue, and SES throttled sending at 14 messages per second. Scaling the worker did not help because SES was the bottleneck.

## Follow-up actions

- Move transactional emails (password resets, receipts) to a separate high-priority queue.
- Request a higher SES sending limit.
