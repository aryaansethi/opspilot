# INC-2026-049: catalog-service deployment stuck with exec format error

Date: 2026-10-14. Severity: SEV-3.

## Summary

A catalog-service deployment never completed. New tasks exited immediately with `exec format error` and the deployment circuit breaker rolled back after 10 failed tasks. Production kept running on the previous version, so customers were not affected.

## Root cause

The CI runner had been changed to an x86 machine and built an amd64-only image, while the service runs on ARM64 Fargate.

## Resolution

The pipeline was changed to build multi-architecture images with buildx.
