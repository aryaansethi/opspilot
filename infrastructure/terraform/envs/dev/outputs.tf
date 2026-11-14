output "api_alb_dns_name" { value = module.alb.dns_name }
output "ecr_repository_url" { value = module.ecr.repository_url }
output "documents_bucket" { value = module.storage.bucket_name }
output "rds_endpoint" { value = module.rds.endpoint }
output "rds_master_secret_arn" { value = module.rds.master_secret_arn }
