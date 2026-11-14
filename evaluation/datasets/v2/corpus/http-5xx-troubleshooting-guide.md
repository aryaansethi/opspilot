# HTTP 5xx Troubleshooting Guide

## 502 Bad Gateway

At the load balancer, 502 means the target closed the connection or sent an invalid response. Common causes are crashes during a request and keep-alive timeout mismatches: the application keep-alive timeout must be longer than the load balancer idle timeout (60 seconds).

## 503 Service Unavailable

503 from the load balancer means there are no healthy targets. Check target health checks and recent deployments.

## 504 Gateway Timeout

504 means the target did not respond within the load balancer idle timeout. Look for slow dependencies such as databases or third-party APIs.

## Application 500 errors

500 responses come from the application itself. Search logs for stack traces with the request ID from the `X-Request-Id` header.
