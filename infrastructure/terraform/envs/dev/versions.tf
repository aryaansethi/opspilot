terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
  # Local state by default. For shared use, configure an S3 backend with locking here.
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "opspilot", Environment = "dev", ManagedBy = "terraform" }
  }
}
