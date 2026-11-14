# Deployment Failures Guide

## Tasks fail health checks and the deployment never finishes

If new ECS tasks start but fail the load balancer health check, the deployment keeps replacing them until the deployment circuit breaker rolls back after 10 failed tasks. Check the task's container logs for start-up errors and confirm the health check path returns 200 within the 5 second timeout.

## CannotPullContainerError

`CannotPullContainerError` means ECS could not download the image: the tag does not exist in ECR, or the task execution role lacks `ecr:GetAuthorizationToken` and `ecr:BatchGetImage`. Confirm the tag that the pipeline pushed.

## ResourceInitializationError for secrets

`ResourceInitializationError: unable to pull secrets or registry auth` means the task execution role cannot read a Secrets Manager secret referenced in the task definition, or the secret ARN is wrong.

## exec format error

`exec format error` at container start means the image was built for a different CPU architecture than the task (for example an amd64 image on ARM64 Fargate). Build multi-architecture images or match the task's `cpuArchitecture`.

## Rolling back

A failed deployment can be rolled back by redeploying the previous task definition revision. If the circuit breaker already rolled back, find the failing revision in the service events before retrying.
