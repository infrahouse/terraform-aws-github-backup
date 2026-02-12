# ── Replica S3 bucket (cross-region) ─────────────────────────────
# Uses AWS provider v6 per-resource region — no aliased providers.

resource "aws_s3_bucket" "replica" {
  region        = var.replica_region
  bucket        = "${local.bucket_name}-replica"
  force_destroy = var.force_destroy

  lifecycle {
    precondition {
      condition     = var.replica_region != data.aws_region.current.name
      error_message = "replica_region must differ from the current region (${data.aws_region.current.name})."
    }
  }

  tags = merge(
    {
      Name = "${local.bucket_name}-replica"
    },
    local.all_tags,
  )
}

resource "aws_s3_bucket_versioning" "replica" {
  region = var.replica_region
  bucket = aws_s3_bucket.replica.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "replica" {
  region = var.replica_region
  bucket = aws_s3_bucket.replica.id

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

resource "aws_s3_bucket_public_access_block" "replica" {
  region = var.replica_region
  bucket = aws_s3_bucket.replica.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "replica" {
  region = var.replica_region
  bucket = aws_s3_bucket.replica.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ── Replication IAM role ────────────────────────────────────────

data "aws_iam_policy_document" "replication_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "replication" {
  name_prefix        = "${var.service_name}-s3-repl-"
  assume_role_policy = data.aws_iam_policy_document.replication_assume_role.json
  tags               = local.all_tags
}

data "aws_iam_policy_document" "replication_permissions" {
  # Source bucket permissions
  statement {
    actions = [
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
    ]
    resources = [
      module.backup_bucket.bucket_arn,
    ]
  }

  statement {
    actions = [
      "s3:GetObjectVersionForReplication",
      "s3:GetObjectVersionAcl",
      "s3:GetObjectVersionTagging",
    ]
    resources = [
      "${module.backup_bucket.bucket_arn}/*",
    ]
  }

  # Destination bucket permissions
  statement {
    actions = [
      "s3:ReplicateObject",
      "s3:ReplicateDelete",
      "s3:ReplicateTags",
    ]
    resources = [
      "${aws_s3_bucket.replica.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "replication" {
  name_prefix = "${var.service_name}-s3-repl-"
  role        = aws_iam_role.replication.id
  policy      = data.aws_iam_policy_document.replication_permissions.json
}

# ── Replication configuration ───────────────────────────────────

resource "aws_s3_bucket_replication_configuration" "backup" {
  # Must have versioning enabled first
  depends_on = [aws_s3_bucket_versioning.replica]

  role   = aws_iam_role.replication.arn
  bucket = module.backup_bucket.bucket_name

  rule {
    id     = "replicate-backups"
    status = "Enabled"
    filter {}

    delete_marker_replication {
      status = "Enabled"
    }

    destination {
      bucket        = aws_s3_bucket.replica.arn
      storage_class = "STANDARD"
    }
  }
}
