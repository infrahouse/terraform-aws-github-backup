variable "region" {
  description = "AWS region for the primary (backup source) deployment."
  type        = string
}

variable "environment" {
  description = "Environment name (lowercase letters/numbers/underscores only)."
  type        = string
}

variable "github_app_id" {
  description = "The GitHub App ID (from the App's settings page)."
  type        = string
}

variable "github_app_installation_id" {
  description = "Installation ID of the GitHub App on the target organization."
  type        = string
}

variable "alarm_emails" {
  description = "Email addresses for CloudWatch alarm notifications."
  type        = list(string)
}

variable "github_app_key_secret_writers" {
  description = <<-EOT
    IAM role ARNs allowed to write the GitHub App PEM into the
    module-managed Secrets Manager secret.
  EOT
  type        = list(string)
}

variable "replica_region" {
  description = "AWS region for the cross-region S3 replica bucket (must differ from region)."
  type        = string
}

variable "subnets" {
  description = "Subnet IDs for the Fargate task (must have outbound internet access)."
  type        = list(string)
}
