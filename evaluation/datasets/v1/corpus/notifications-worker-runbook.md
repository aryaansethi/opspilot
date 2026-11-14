# Notifications Worker Runbook

Service: notifications-worker. Owner: Growth Platform team.

## Queue backlog

Notifications are read from the `notifications-queue` SQS queue. Page the owner if `ApproximateAgeOfOldestMessage` is above 600 seconds for 10 minutes.
Scale the worker from 3 to 10 tasks during backlogs; the email provider limit is the real ceiling.

## Email provider throttling

Emails are sent through Amazon SES with a sending limit of 14 messages per second. Throttled sends log `Throttling: Maximum sending rate exceeded` and are retried with backoff.

## Poison messages

Messages that fail 5 times move to `notifications-dlq`. Inspect them before redriving; a malformed template variable is the most common cause.

## Required configuration

The worker needs `SMTP_FROM_ADDRESS`, `SES_REGION` and `TEMPLATE_BUCKET` environment variables. It exits on start-up if any is missing.
