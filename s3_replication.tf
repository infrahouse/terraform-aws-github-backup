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
# policy, may be replaced.
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
