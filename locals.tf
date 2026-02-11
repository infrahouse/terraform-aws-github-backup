locals {
  module_version = "1.0.0"
  # 1 vCPU / 2 GB — sufficient for sequential git-clone + bundle
  # operations.  Cloning is mostly I/O-bound (network + disk), so
  # additional CPU gives diminishing returns.
  task_cpu    = 1024
  task_memory = 2048

  # 50 GB ephemeral storage — must be large enough to hold the
  # biggest single repository mirror + its git bundle at the same
  # time.  Each repo is cloned, bundled, uploaded, then cleaned up
  # before the next one starts, so this only needs to fit one repo.
  task_ephemeral_storage_gb = 50

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
