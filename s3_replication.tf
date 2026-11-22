# ── Cross-region replication state migration ─────────────────────
# Up to 2.0.2, the replica bucket, its settings, and the replication
# configuration were hand-rolled in this file. They are now provisioned by
# the `backup_bucket` module (s3.tf) via its `replication_region` input,
# and both lifecycle configurations share one for_each resource in s3.tf.
#
# A bucket has only one versioning configuration, one public access block,
# one encryption configuration, one replication configuration, and one
# lifecycle configuration. The resources at the old and new addresses
# write the same bucket setting, so they must be moved, not recreated:
# Terraform does not order a destroy at the old address after the create
# at the new one, and if the destroy lands last it wipes the setting the
# create just wrote (e.g. suspends replica versioning or drops
# replication) while state still lists it.
#
# Only standalone objects, such as the replication IAM role and its
# policy, may be replaced. This module keeps its own role anyway (see
# below), so an upgrade from 2.0.1 or 2.0.2 replaces nothing.
#
# The `from` addresses are the 2.0.1 and 2.0.2 addresses (identical in
# both releases).

moved {
  from = aws_s3_bucket.replica
  to   = module.backup_bucket.aws_s3_bucket.replica[0]
}

moved {
  from = aws_s3_bucket_versioning.replica
  to   = module.backup_bucket.aws_s3_bucket_versioning.replica[0]
}

moved {
  from = aws_s3_bucket_public_access_block.replica
  to   = module.backup_bucket.aws_s3_bucket_public_access_block.replica[0]
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.replica
  to   = module.backup_bucket.aws_s3_bucket_server_side_encryption_configuration.replica[0]
}

moved {
  from = aws_s3_bucket_replication_configuration.backup
  to   = module.backup_bucket.aws_s3_bucket_replication_configuration.this[0]
}

moved {
  from = aws_s3_bucket_lifecycle_configuration.backup
  to   = aws_s3_bucket_lifecycle_configuration.backup["source"]
}

moved {
  from = aws_s3_bucket_lifecycle_configuration.replica
  to   = aws_s3_bucket_lifecycle_configuration.backup["replica"]
}

# ── Replication IAM role ─────────────────────────────────────────
# The `backup_bucket` module replicates with this role (its
# `replication_role_arn` input) and creates none of its own. Replication
# must never point at a deleted role: S3 doesn't retry the objects that
# fail to replicate.
#
# This is the role 2.0.1 and 2.0.2 created, at the same address and with
# the same name prefix, so upgrading from them leaves it as it is. Had the
# module created its own role instead, Terraform would delete this one
# before it moved replication to the new role: for a deleted object it
# reads create_before_destroy from the state, and the 2.0.1/2.0.2 state
# doesn't have it (infrahouse/terraform-aws-s3-bucket#34).
#
# 2.0.3 replicated with the module's role. The two moved blocks below take
# that role and its policy over. Their names differ from these, so
# Terraform replaces them, and create_before_destroy makes it create the
# new role and policy, move replication to them, and only then delete the
# old ones.

moved {
  from = module.backup_bucket.aws_iam_role.replication[0]
  to   = aws_iam_role.replication
}

moved {
  from = module.backup_bucket.aws_iam_role_policy.replication[0]
  to   = aws_iam_role_policy.replication
}

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

  lifecycle {
    create_before_destroy = true
  }
}

data "aws_iam_policy_document" "replication_permissions" {
  # Source bucket permissions
  statement {
    actions = [
      "s3:GetReplicationConfiguration",
      "s3:ListBucket",
    ]
    resources = [
      local.bucket_arn,
    ]
  }

  statement {
    actions = [
      "s3:GetObjectVersionForReplication",
      "s3:GetObjectVersionAcl",
      "s3:GetObjectVersionTagging",
    ]
    resources = [
      "${local.bucket_arn}/*",
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
      "${local.replica_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "replication" {
  name_prefix = "${var.service_name}-s3-repl-"
  role        = aws_iam_role.replication.id
  policy      = data.aws_iam_policy_document.replication_permissions.json

  # Without this, a replacement deletes the old policy first, and the old
  # role keeps serving replication without permissions until replication
  # moves to the new role.
  lifecycle {
    create_before_destroy = true
  }
}
