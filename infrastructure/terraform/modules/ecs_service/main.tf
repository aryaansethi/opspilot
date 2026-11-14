# One Fargate service: task definition, log group, security group, and a task role
# whose permissions are passed in (least privilege per process).

variable "name" { type = string }
variable "cluster_arn" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "image" { type = string }
variable "command" { type = list(string) }
variable "cpu" {
  type    = number
  default = 256
}
variable "memory" {
  type    = number
  default = 512
}
variable "port" {
  type    = number
  default = null
}
variable "environment" {
  type    = map(string)
  default = {}
}
variable "secrets" {
  description = "Env var name => Secrets Manager ARN (optionally with :json-key::)"
  type        = map(string)
  default     = {}
}
variable "task_policy_json" {
  type    = string
  default = null
}
variable "ingress_security_group_ids" {
  type    = list(string)
  default = []
}
variable "target_group_arn" {
  type    = string
  default = null
}
variable "execution_role_arn" { type = string }
variable "service_registry_arn" {
  description = "Cloud Map service ARN, to give this service a private DNS name"
  type        = string
  default     = null
}
variable "desired_count" {
  type    = number
  default = 1
}
variable "log_retention_days" {
  type    = number
  default = 7
}

data "aws_region" "current" {}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "task" {
  count  = var.task_policy_json == null ? 0 : 1
  name   = "${var.name}-task"
  role   = aws_iam_role.task.id
  policy = var.task_policy_json
}

resource "aws_security_group" "this" {
  name   = var.name
  vpc_id = var.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.this.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_ingress_rule" "from" {
  for_each                     = var.port == null ? toset([]) : toset(var.ingress_security_group_ids)
  security_group_id            = aws_security_group.this.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = var.port
  to_port                      = var.port
}

resource "aws_ecs_task_definition" "this" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name         = var.name
    image        = var.image
    command      = var.command
    essential    = true
    portMappings = var.port == null ? [] : [{ containerPort = var.port, protocol = "tcp" }]
    environment  = [for k, v in var.environment : { name = k, value = v }]
    secrets      = [for k, v in var.secrets : { name = k, valueFrom = v }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this.name
        awslogs-region        = data.aws_region.current.name
        awslogs-stream-prefix = var.name
      }
    }
  }])
}

resource "aws_ecs_service" "this" {
  name            = var.name
  cluster         = var.cluster_arn
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.this.id]
    assign_public_ip = true
  }
  dynamic "load_balancer" {
    for_each = var.target_group_arn == null ? [] : [1]
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.name
      container_port   = var.port
    }
  }
  dynamic "service_registries" {
    for_each = var.service_registry_arn == null ? [] : [1]
    content {
      registry_arn = var.service_registry_arn
    }
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

output "security_group_id" { value = aws_security_group.this.id }
output "task_role_name" { value = aws_iam_role.task.name }
