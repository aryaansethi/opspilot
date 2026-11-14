# INC-2026-034: Search returning errors after cluster turned red

Date: 2026-07-09. Severity: SEV-2. Duration: 1 hour 20 minutes.

## Summary

About 30 percent of product searches failed. The OpenSearch cluster health was red.

## Root cause

A data node reached the 95 percent disk flood-stage watermark after old log indices were not deleted. Indices on that node became read-only and two primary shards were unassigned.

## Resolution

Old indices were deleted, the read-only block was removed, and shards were reallocated.

## Follow-up actions

- Add an index lifecycle policy that deletes log indices after 14 days.
- Alert at 80 percent disk usage.
