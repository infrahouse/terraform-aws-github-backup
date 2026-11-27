locals {
  module_version = "2.1.0"

  task_cpu                  = var.task_cpu
  task_memory               = var.task_memory
  task_ephemeral_storage_gb = var.task_ephemeral_storage_gb

  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  # Auto-generate bucket name if not provided
  bucket_name = (
    var.s3_bucket_name != null
    ? var.s3_bucket_name
    : "${var.service_name}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.name}"
  )

  # The replication role's policy builds the bucket ARNs instead of reading
  # the backup_bucket module's outputs. The source bucket's output would
  # form a cycle: the module's source bucket depends on
  # replication_role_arn, which comes from that policy (see s3.tf). The
  # replica's output would make Terraform force the policy's
  # create_before_destroy onto the replica bucket. The module names the
  # replica "<bucket_name>-replica"; a check in s3_replication.tf compares
  # both ARNs with the module's outputs.
  bucket_arn         = "arn:${local.partition}:s3:::${local.bucket_name}"
  replica_bucket_arn = "${local.bucket_arn}-replica"

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

  # The ECS cluster and its Container Insights log group both take their
  # names from here, so the group's name doesn't depend on the cluster
  # resource: the cluster has to depend on the group instead (see
  # time_sleep.container_insights_destroy_delay in cloudwatch.tf).
  cluster_name = var.service_name

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
