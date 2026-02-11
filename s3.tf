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
}
