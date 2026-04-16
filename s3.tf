module "backup_bucket" {
  source  = "registry.infrahouse.com/infrahouse/s3-bucket/aws"
  version = "0.3.1"

  bucket_name       = local.bucket_name
  enable_versioning = true
  force_destroy     = var.force_destroy

  tags = merge(
    {
      Name           = local.bucket_name
      module_version = local.module_version
    },
    local.all_tags,
  )
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket = module.backup_bucket.bucket_name

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

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
