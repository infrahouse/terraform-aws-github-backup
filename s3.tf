module "backup_bucket" {
  source  = "registry.infrahouse.com/infrahouse/s3-bucket/aws"
  version = "0.10.0"

  bucket_name       = local.bucket_name
  enable_versioning = true
  force_destroy     = var.force_destroy

  # The module provisions the cross-region replica bucket, its SSL-only
  # bucket policy, and the replication configuration on the source bucket.
  # It also tags the replica so the Vanta
  # "aws-s3-cross-region-replication-enabled" check treats it as a
  # destination (exempt) rather than an unreplicated source.
  replication_region = var.replica_region

  # Replicate with this module's role (s3_replication.tf explains why).
  # The module decides at plan time whether to create its own role, so it
  # must know then that this isn't null. aws_iam_role.replication.arn is
  # unknown until a new role exists; a string template is known to be
  # non-null. The name comes from the policy rather than the role, so the
  # replication configuration also waits for the policy: otherwise S3 could
  # replicate with a role that has no permissions yet.
  replication_role_arn = "arn:${local.partition}:iam::${local.account_id}:role/${aws_iam_role_policy.replication.role}"

  tags = merge(
    {
      Name           = local.bucket_name
      module_version = local.module_version
    },
    local.all_tags,
  )
}

# One lifecycle config per bucket (source + replica). The replica needs its
# own copy because S3 does not replicate lifecycle-driven expirations, so
# without it the DR copy would grow unbounded. See local.lifecycle_buckets.
resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  for_each = local.lifecycle_buckets

  region = each.value.region
  bucket = each.value.bucket

  rule {
    id     = local.backup_lifecycle_rule.id
    status = local.backup_lifecycle_rule.status

    filter {
      prefix = local.backup_lifecycle_rule.prefix
    }

    expiration {
      days = local.backup_lifecycle_rule.days
    }

    noncurrent_version_expiration {
      noncurrent_days = local.backup_lifecycle_rule.days
    }
  }

  # Clean up stuck multipart uploads so orphaned parts don't accumulate
  # storage charges if a bundle upload is interrupted mid-flight.
  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    # filter {} = bucket-wide, intentionally broader than the expiration
    # rule's `github-backup/` prefix: stray multipart parts (from direct
    # puts to the bucket root or dropped uploads at any key) still get
    # reaped. Do not "fix" this to match the expiration prefix.
    filter {}

    # A bundle upload that hasn't completed in 24 hours is a failed task
    # run, not an in-flight upload. One day is enough to let the next
    # scheduled run start fresh without stale parts.
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}
