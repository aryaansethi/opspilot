# Infrastructure (AWS, Terraform)

**Status: written and validated, never applied.** `terraform validate` and `fmt` run in CI with no AWS
credentials. Running `terraform apply` would create paid resources, and that's the owner's decision.

## What `envs/dev` would create

| Area | Resources |
|---|---|
| Cost guard | AWS Budget with email alerts at 50/80/100% (`monthly_budget_usd`, default 30) |
| Network | VPC, 2 public + 2 private subnets, internet gateway. **No NAT Gateway** (a large fixed cost) |
| Ingress | ALB with HTTPS (TLS 1.3 policy), HTTP→HTTPS redirect; needs an ACM certificate |
| Compute | ECS Fargate (ARM64): `api`, `worker`, `mcp-cloudwatch`, `mcp-github`, one image from ECR |
| Data | RDS PostgreSQL 16 (`db.t4g.micro`, encrypted, private, single-AZ); S3 bucket (private, encrypted); SQS `ingest`/`investigate`/`evaluate` queues with DLQs |
| Secrets | Secrets Manager entries created **empty**; values are set by hand and never stored in Terraform state |
| Service discovery | Cloud Map private DNS for the MCP servers (only reachable from the API and worker) |
| Monitoring | Per-service log groups (7-day retention), ALB 5xx alarm, DLQ-not-empty alarms |

## Least privilege

- `api`: put/get/delete objects under `ws/` in the documents bucket; send to the queues.
- `worker`: read objects; receive and delete queue messages.
- `mcp-cloudwatch`: `logs:FilterLogEvents` on the allowlisted log groups only, plus read-only metric
  and alarm APIs (these don't support resource scoping, so the server also enforces a namespace
  allowlist).
- `mcp-github`: no AWS permissions; it is the only service that can read the GitHub token secret.

## Cost risks (check current prices in the AWS Pricing Calculator for your region)

The always-on items are the ALB, the RDS instance, four Fargate tasks and their public IPv4
addresses, plus CloudWatch log ingestion and Secrets Manager secrets. No cost estimate is given here
because it depends on region, hours running and current pricing. To keep costs down: scale ECS services
to 0 and stop RDS between demos, or `terraform destroy`.

## Decisions still open (the owner's call)

1. **Whether to deploy at all.** Local Docker Compose plus a demo video costs nothing.
2. **Where the models run.** Ollama is local-only; on AWS the backend needs an OpenAI-compatible endpoint
   (`llm_base_url`): a hosted API (paid per token) or a GPU instance (expensive). This is why `LLM_*`
   values are variables with no defaults.
3. **Domain and certificate** for the API (and the Vercel frontend origin for CORS).
4. **Terraform state backend** (S3 + locking) if more than one person applies.

## Commands (only once the decisions above are made)

```bash
cd infrastructure/terraform/envs/dev
cp terraform.tfvars.example terraform.tfvars   # fill in; git-ignored
terraform init
terraform plan                                 # review every resource before any apply
```
