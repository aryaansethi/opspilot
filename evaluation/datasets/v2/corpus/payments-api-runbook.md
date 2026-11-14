# Payments API Runbook

Service: payments-api. Owner: Payments team. Pager rotation: payments-oncall.

## Card authorization failures

Symptom: checkout shows "Payment could not be processed" and logs contain `PAY_GATEWAY_502`.
`PAY_GATEWAY_502` means the external card gateway returned a bad gateway response. Check the gateway status page first.
If more than 5 percent of authorizations fail for 10 minutes, enable the fallback acquirer with the `payments.fallback_acquirer` flag.

## Idempotency key conflicts

Error `IDEMP_409` is returned when a client retries a payment with the same idempotency key but a different amount.
Idempotency keys are stored in Redis for 24 hours. Do not flush the idempotency Redis database: it can cause double charges.

## Webhook backlog

Gateway webhooks are queued in the `payments-webhooks` SQS queue. If the oldest message is older than 15 minutes, scale the webhook consumer from 2 to 6 tasks.

## Rotating the gateway API key

Rotate the gateway API key every 90 days. Create the new key in the gateway console, store it in Secrets Manager under `payments/gateway-key`, then restart payments-api tasks one at a time.
