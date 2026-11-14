# OpsPilot dev environment on AWS: ALB → ECS Fargate (api, worker, two MCP servers),
# RDS PostgreSQL 16, S3, SQS, Secrets Manager, CloudWatch, and a cost budget.
# This is written and validated but NOT applied. Applying creates paid resources.

data "aws_caller_identity" "current" {}

module "budget" {
  source            = "../../modules/budgets"
  name              = var.name
  monthly_limit_usd = var.monthly_budget_usd
  alert_emails      = var.alert_emails
}

module "network" {
  source = "../../modules/network"
  name   = var.name
  azs    = var.azs
}

module "ecr" {
  source = "../../modules/ecr"
  name   = var.name
}

module "storage" {
  source       = "../../modules/storage"
  name         = var.name
  cors_origins = var.frontend_origins
}

module "alb" {
  source          = "../../modules/alb"
  name            = var.name
  vpc_id          = module.network.vpc_id
  subnet_ids      = module.network.public_subnet_ids
  certificate_arn = var.certificate_arn
}

module "rds" {
  source                     = "../../modules/rds"
  name                       = var.name
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.private_subnet_ids
  allowed_security_group_ids = [module.api.security_group_id, module.worker.security_group_id]
}

# Secrets are created empty; values are set by an operator (never stored in Terraform state):
#   database-url  postgresql+asyncpg://opspilot:<password from the RDS-managed secret>@<rds endpoint>:5432/opspilot
#   jwt-secret    python -c "import secrets; print(secrets.token_urlsafe(48))"
#   llm-api-key   key for the chosen model endpoint
#   github-token  fine-grained, read-only PAT
resource "aws_secretsmanager_secret" "app" {
  for_each                = toset(["database-url", "jwt-secret", "llm-api-key", "github-token"])
  name                    = "${var.name}/${each.key}"
  recovery_window_in_days = 7
}

resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "disabled" # enable when the extra CloudWatch cost is acceptable
  }
}

data "aws_iam_policy_document" "execution_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.execution_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [for s in aws_secretsmanager_secret.app : s.arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.name}-execution-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

locals {
  image = "${module.ecr.repository_url}:${var.image_tag}"
  common_env = {
    ENVIRONMENT           = "production"
    COOKIE_SECURE         = "true"
    AWS_REGION            = var.region
    S3_DOCUMENTS_BUCKET   = module.storage.bucket_name
    SQS_INGEST_QUEUE      = module.storage.queue_names["ingest"]
    SQS_INVESTIGATE_QUEUE = module.storage.queue_names["investigate"]
    SQS_EVALUATE_QUEUE    = module.storage.queue_names["evaluate"]
    CORS_ORIGINS          = jsonencode(var.frontend_origins)
    LLM_BASE_URL          = var.llm_base_url
    LLM_MODEL             = var.llm_model
    LLM_PROMPT_SUFFIX     = ""
    EMBEDDING_MODEL       = var.embedding_model
    EMBEDDING_DIM         = tostring(var.embedding_dim)
    MCP_CLOUDWATCH_URL    = "http://${module.mcp_cloudwatch_discovery.dns_name}:8101/mcp"
    MCP_GITHUB_URL        = "http://${module.mcp_github_discovery.dns_name}:8102/mcp"
    AWS_ENDPOINT_URL      = ""
  }
  app_secrets = {
    DATABASE_URL = aws_secretsmanager_secret.app["database-url"].arn
    JWT_SECRET   = aws_secretsmanager_secret.app["jwt-secret"].arn
    LLM_API_KEY  = aws_secretsmanager_secret.app["llm-api-key"].arn
  }
  queue_arns = values(module.storage.queue_arns)
}

# ---- private DNS names for the MCP servers (Cloud Map), reachable only inside the VPC
resource "aws_service_discovery_private_dns_namespace" "this" {
  name = "${var.name}.internal"
  vpc  = module.network.vpc_id
}

module "mcp_cloudwatch_discovery" {
  source       = "./discovery"
  name         = "mcp-cloudwatch"
  namespace_id = aws_service_discovery_private_dns_namespace.this.id
  namespace    = aws_service_discovery_private_dns_namespace.this.name
}

module "mcp_github_discovery" {
  source       = "./discovery"
  name         = "mcp-github"
  namespace_id = aws_service_discovery_private_dns_namespace.this.id
  namespace    = aws_service_discovery_private_dns_namespace.this.name
}

# ---- least-privilege task policies
data "aws_iam_policy_document" "api" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${module.storage.bucket_arn}/ws/*"]
  }
  statement {
    actions   = ["sqs:SendMessage", "sqs:GetQueueUrl"]
    resources = local.queue_arns
  }
}

data "aws_iam_policy_document" "worker" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${module.storage.bucket_arn}/ws/*"]
  }
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
    resources = local.queue_arns
  }
}

data "aws_iam_policy_document" "mcp_cloudwatch" {
  statement {
    sid       = "ReadAllowlistedLogGroups"
    actions   = ["logs:FilterLogEvents", "logs:DescribeLogGroups"]
    resources = length(var.cloudwatch_log_groups) == 0 ? ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/opspilot-none:*"] : [for g in var.cloudwatch_log_groups : "arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:${g}:*"]
  }
  statement {
    # These CloudWatch read APIs do not support resource-level permissions; the MCP
    # server additionally enforces the namespace allowlist.
    sid       = "ReadMetricsAndAlarms"
    actions   = ["cloudwatch:GetMetricData", "cloudwatch:ListMetrics", "cloudwatch:DescribeAlarms", "cloudwatch:DescribeAlarmHistory"]
    resources = ["*"]
  }
}

# ---- services
module "api" {
  source                     = "../../modules/ecs_service"
  name                       = "${var.name}-api"
  cluster_arn                = aws_ecs_cluster.this.arn
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.public_subnet_ids
  image                      = local.image
  command                    = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
  cpu                        = 512
  memory                     = 1024
  port                       = 8000
  ingress_security_group_ids = [module.alb.security_group_id]
  target_group_arn           = module.alb.target_group_arn
  environment                = local.common_env
  secrets                    = local.app_secrets
  task_policy_json           = data.aws_iam_policy_document.api.json
  execution_role_arn         = aws_iam_role.execution.arn
}

module "worker" {
  source             = "../../modules/ecs_service"
  name               = "${var.name}-worker"
  cluster_arn        = aws_ecs_cluster.this.arn
  vpc_id             = module.network.vpc_id
  subnet_ids         = module.network.public_subnet_ids
  image              = local.image
  command            = ["python", "-m", "app.worker"]
  cpu                = 512
  memory             = 2048
  environment        = local.common_env
  secrets            = local.app_secrets
  task_policy_json   = data.aws_iam_policy_document.worker.json
  execution_role_arn = aws_iam_role.execution.arn
}

module "mcp_cloudwatch" {
  source                     = "../../modules/ecs_service"
  name                       = "${var.name}-mcp-cloudwatch"
  cluster_arn                = aws_ecs_cluster.this.arn
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.public_subnet_ids
  image                      = local.image
  command                    = ["python", "-m", "mcp_servers.cloudwatch.server"]
  port                       = 8101
  ingress_security_group_ids = [module.api.security_group_id, module.worker.security_group_id]
  environment = {
    MCP_PORT              = "8101"
    AWS_REGION            = var.region
    AWS_ENDPOINT_URL      = ""
    CW_ALLOWED_LOG_GROUPS = join(",", var.cloudwatch_log_groups)
    CW_ALLOWED_NAMESPACES = join(",", var.cloudwatch_namespaces)
  }
  task_policy_json     = data.aws_iam_policy_document.mcp_cloudwatch.json
  execution_role_arn   = aws_iam_role.execution.arn
  service_registry_arn = module.mcp_cloudwatch_discovery.arn
}

module "mcp_github" {
  source                     = "../../modules/ecs_service"
  name                       = "${var.name}-mcp-github"
  cluster_arn                = aws_ecs_cluster.this.arn
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.public_subnet_ids
  image                      = local.image
  command                    = ["python", "-m", "mcp_servers.github.server"]
  port                       = 8102
  ingress_security_group_ids = [module.api.security_group_id, module.worker.security_group_id]
  environment = {
    MCP_PORT             = "8102"
    GITHUB_ALLOWED_REPOS = join(",", var.github_repositories)
  }
  # Only this service can read the GitHub token.
  secrets              = { GITHUB_TOKEN = aws_secretsmanager_secret.app["github-token"].arn }
  execution_role_arn   = aws_iam_role.execution.arn
  service_registry_arn = module.mcp_github_discovery.arn
}

# ---- alarms (actions left empty: add an SNS topic when there is an on-call destination)
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name}-api-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = module.alb.arn_suffix }
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each            = toset(["ingest", "investigate", "evaluate"])
  alarm_name          = "${var.name}-${each.key}-dlq-not-empty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = "${var.name}-${each.key}-dlq" }
}
