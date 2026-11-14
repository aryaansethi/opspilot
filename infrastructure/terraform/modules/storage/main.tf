# Private document bucket and the three SQS queues (each with a dead-letter queue).

variable "name" { type = string }
variable "cors_origins" { type = list(string) }

resource "aws_s3_bucket" "documents" {
  bucket_prefix = "${var.name}-documents-"
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_cors_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  cors_rule {
    allowed_methods = ["PUT"]
    allowed_origins = var.cors_origins
    allowed_headers = ["Content-Type"]
    max_age_seconds = 3000
  }
}

locals {
  queues = {
    ingest      = { visibility = 300, receives = 3 }
    investigate = { visibility = 600, receives = 2 }
    evaluate    = { visibility = 7200, receives = 1 }
  }
}

resource "aws_sqs_queue" "dlq" {
  for_each                  = local.queues
  name                      = "${var.name}-${each.key}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "main" {
  for_each                   = local.queues
  name                       = "${var.name}-${each.key}"
  visibility_timeout_seconds = each.value.visibility
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = each.value.receives
  })
}

output "bucket_name" { value = aws_s3_bucket.documents.bucket }
output "bucket_arn" { value = aws_s3_bucket.documents.arn }
output "queue_names" { value = { for k, q in aws_sqs_queue.main : k => q.name } }
output "queue_arns" { value = { for k, q in aws_sqs_queue.main : k => q.arn } }
