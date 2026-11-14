# A Cloud Map service so an ECS service gets a private DNS name.
variable "name" { type = string }
variable "namespace_id" { type = string }
variable "namespace" { type = string }

resource "aws_service_discovery_service" "this" {
  name = var.name
  dns_config {
    namespace_id = var.namespace_id
    dns_records {
      type = "A"
      ttl  = 10
    }
  }
}

output "dns_name" { value = "${var.name}.${var.namespace}" }
output "arn" { value = aws_service_discovery_service.this.arn }
