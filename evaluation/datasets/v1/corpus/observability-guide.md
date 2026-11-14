# Observability Guide

## Logs

Each ECS service logs to a CloudWatch log group named `/ecs/<service>`, for example `/ecs/orders-api`. Logs are retained for 30 days.

## Metrics

Custom application metrics are published to the CloudWatch namespace `OpsPilot/<ServiceName>`, for example `OpsPilot/OrdersApi`, with a `Service` dimension.

## Request tracing

Every request carries an `X-Request-Id` header. Include it in log lines so a request can be followed across services.

## Alarms

Every service has a p95 latency alarm named `<service>-p95-latency` and a 5xx rate alarm named `<service>-5xx-rate`.
