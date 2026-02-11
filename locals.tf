locals {
  module_version = "2.0.0"

  task_cpu                  = var.task_cpu
  task_memory               = var.task_memory
  task_ephemeral_storage_gb = var.task_ephemeral_storage_gb

  # Auto-generate bucket name if not provided
  bucket_name = (
    var.s3_bucket_name != null
    ? var.s3_bucket_name
    : "${var.service_name}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.name}"
  )

  # Shared lifecycle rule for source and replica buckets.
  # Keeps backup retention consistent across both regions.
  backup_lifecycle_rule = {
    id     = "expire-old-backups"
    status = var.backup_retention_days > 0 ? "Enabled" : "Disabled"
    prefix = "github-backup/"
    days   = var.backup_retention_days > 0 ? var.backup_retention_days : 1
  }

  default_module_tags = {
    environment       = var.environment
    service           = var.service_name
    account           = data.aws_caller_identity.current.account_id
    created_by_module = "infrahouse/github-backup/aws"
  }

  all_tags = merge(
    local.default_module_tags,
    var.tags,
  )
}
