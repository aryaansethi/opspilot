# Deployment Guide

## Pipeline stages

Every service deploys through the same pipeline: build, unit tests, image scan, deploy to staging, smoke tests, canary in production, full rollout.

## Canary releases

The canary receives 10 percent of production traffic for 15 minutes. The pipeline rolls back automatically if the canary 5xx rate exceeds 2 percent or p95 latency doubles.

## Configuration changes

Configuration values ship with the release in `application.yml` or task definition environment variables. Configuration-only changes still go through the canary stage.

## Database migrations

Use expand-and-contract migrations: add new columns first, deploy code that writes both, then remove old columns in a later release. Never drop a column in the same release that stops using it.

## Manual rollback

Roll back by redeploying the previous task definition from the pipeline. Rollbacks skip the canary stage.
