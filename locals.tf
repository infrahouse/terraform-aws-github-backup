locals {
  module_version = "2.0.3"

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

  # Buckets that share the backup retention lifecycle. The source uses the
  # provider's default region (region = null); the replica lives in another
  # region, set per-resource (provider v6, no aliased provider). The replica
  # needs its own lifecycle because S3 does not replicate lifecycle-driven
  # expirations from the source.
  lifecycle_buckets = {
    source = {
      bucket = module.backup_bucket.bucket_name
      region = null
    }
    replica = {
      bucket = module.backup_bucket.replica_bucket_name
      region = var.replica_region
    }
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
