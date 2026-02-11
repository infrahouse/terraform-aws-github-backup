# ── Required ─────────────────────────────────────────────────────

variable "github_app_id" {
  description = "The GitHub App ID. Found in the App's settings page."
  type        = string
}

variable "github_app_installation_id" {
  description = <<-EOT
    The installation ID of the GitHub App on
    the target organization.
  EOT
  type        = string
}

variable "alarm_emails" {
  description = <<-EOT
    List of email addresses to receive CloudWatch alarm
    notifications. AWS will send confirmation emails that
    must be accepted.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.alarm_emails) > 0
    error_message = "At least one email address must be provided for alarm notifications."
  }

  validation {
    condition = alltrue([
      for email in var.alarm_emails :
      can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", email))
    ])
    error_message = "All alarm_emails must be valid email addresses."
  }
}

variable "replica_region" {
  description = <<-EOT
    AWS region for cross-region backup replication.
  EOT
  type        = string
}

variable "github_app_key_secret_writers" {
  description = <<-EOT
    List of IAM role ARNs that are allowed to write
    the GitHub App private key (PEM) into the secret
    created by this module.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.github_app_key_secret_writers) > 0
    error_message = "At least one writer ARN is required to populate the secret."
  }
}

variable "subnets" {
  description = <<-EOT
    List of subnet IDs for the Fargate task.
    The subnets must have outbound internet access
    (GitHub API, S3, etc.) — either private subnets
    with a NAT gateway or public subnets.
    Public IP assignment is detected automatically
    from the subnet configuration.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.subnets) >= 1
    error_message = <<-EOT
      At least one subnet is required.
      Provided: ${length(var.subnets)}
    EOT
  }
}

# ── Optional ─────────────────────────────────────────────────────

variable "environment" {
  description = "Name of environment."
  type        = string
  default     = "development"

  validation {
    condition     = can(regex("^[a-z0-9_]+$", var.environment))
    error_message = <<-EOT
      environment must contain only lowercase letters,
      numbers, and underscores (no hyphens).
      Got: ${var.environment}
    EOT
  }
}

variable "service_name" {
  description = <<-EOT
    Descriptive name of the service.
    Used for naming resources.
  EOT
  type        = string
  default     = "github-backup"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.service_name))
    error_message = "service_name must be lowercase alphanumeric with hyphens, and not start/end with a hyphen."
  }
}

variable "schedule_expression" {
  description = <<-EOT
    EventBridge schedule expression for backup frequency.
    Examples: "rate(1 day)", "cron(0 2 * * ? *)"
  EOT
  type        = string
  default     = "rate(1 day)"

  validation {
    condition     = can(regex("^(rate|cron)\\(", var.schedule_expression))
    error_message = "schedule_expression must start with 'rate(' or 'cron('."
  }
}

variable "backup_retention_days" {
  description = <<-EOT
    Number of days to retain backups in S3 before
    expiration. Set to 0 to disable expiration.
  EOT
  type        = number
  default     = 365

  validation {
    condition     = var.backup_retention_days >= 0
    error_message = <<-EOT
      backup_retention_days must be >= 0.
      Got: ${var.backup_retention_days}
    EOT
  }
}

variable "image_uri" {
  description = <<-EOT
    Docker image URI for the backup runner.
    Defaults to the InfraHouse public ECR image tagged "latest".
    For production use, consider pinning to a specific commit SHA tag
    (e.g., "public.ecr.aws/infrahouse/github-backup:abc1234")
    to avoid unexpected changes.
  EOT
  type        = string
  default     = "public.ecr.aws/infrahouse/github-backup:latest"
}

variable "s3_bucket_name" {
  description = <<-EOT
    Name for the S3 backup bucket.
    If null, a name is auto-generated.
  EOT
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = <<-EOT
    Number of days to retain CloudWatch logs.
  EOT
  type        = number
  default     = 365
}

variable "log_group_kms_key_arn" {
  description = <<-EOT
    ARN of a KMS key to encrypt the CloudWatch Log Group.
    If null, logs are encrypted with the default
    AWS-managed key.
  EOT
  type        = string
  default     = null
}

variable "task_cpu" {
  description = <<-EOT
    CPU units for the Fargate task (1024 = 1 vCPU).
  EOT
  type        = number
  default     = 1024
}

variable "task_memory" {
  description = <<-EOT
    Memory (MiB) for the Fargate task.
  EOT
  type        = number
  default     = 2048
}

variable "task_ephemeral_storage_gb" {
  description = <<-EOT
    Ephemeral storage (GiB) for the Fargate task.
    Must be large enough to hold the biggest single
    repository mirror and its git bundle simultaneously.
  EOT
  type        = number
  default     = 50
}

variable "force_destroy" {
  description = <<-EOT
    Allow destroying S3 buckets even when they contain
    objects. Set to true only for testing.
  EOT
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to all resources."
  type        = map(string)
  default     = {}
}
