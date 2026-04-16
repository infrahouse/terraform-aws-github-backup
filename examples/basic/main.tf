provider "aws" {
  region = var.region

  default_tags {
    tags = {
      created_by  = "infrahouse/terraform-aws-github-backup"
      environment = var.environment
    }
  }
}

module "github_backup" {
  source  = "registry.infrahouse.com/infrahouse/github-backup/aws"
  version = "2.0.2"

  github_app_id              = var.github_app_id
  github_app_installation_id = var.github_app_installation_id

  alarm_emails                  = var.alarm_emails
  github_app_key_secret_writers = var.github_app_key_secret_writers
  replica_region                = var.replica_region
  subnets                       = var.subnets

  environment = var.environment
}
