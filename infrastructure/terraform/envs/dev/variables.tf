variable "region" {
  type    = string
  default = "us-east-1"
}
variable "azs" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}
variable "name" {
  type    = string
  default = "opspilot-dev"
}
variable "image_tag" {
  description = "Backend image tag in ECR (pushed by CI)"
  type        = string
}
variable "certificate_arn" {
  description = "ACM certificate for the API domain (e.g. api.example.com)"
  type        = string
}
variable "frontend_origins" {
  description = "Browser origins allowed by CORS and S3 uploads (the Vercel app URL)"
  type        = list(string)
}
variable "alert_emails" {
  type = list(string)
}
variable "monthly_budget_usd" {
  type    = number
  default = 30
}
variable "llm_base_url" {
  description = "OpenAI-compatible endpoint for the chat/embedding models (hosting choice is open)"
  type        = string
}
variable "llm_model" { type = string }
variable "embedding_model" { type = string }
variable "embedding_dim" { type = number }
variable "cloudwatch_log_groups" {
  description = "Log groups the CloudWatch MCP server may read"
  type        = list(string)
  default     = []
}
variable "cloudwatch_namespaces" {
  type    = list(string)
  default = []
}
variable "github_repositories" {
  type    = list(string)
  default = []
}
