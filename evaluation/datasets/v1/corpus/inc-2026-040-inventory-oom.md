# INC-2026-040: Inventory reconciliation job killed repeatedly

Date: 2026-09-03. Severity: SEV-3.

## Summary

The nightly reconciliation job failed three nights in a row. ECS showed exit code 137 and reason OOMKilled.

## Root cause

A code change made the job load the full product catalog into memory instead of streaming it in pages. Memory use grew past the 2 GB task limit. The JVM heap was set to 1.9 GB, too close to the container limit.

## Resolution

The job was changed back to paged reads and `-Xmx` was set to 1.5 GB.
