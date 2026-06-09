# ── Cross-region replication state migration ─────────────────────
# The replica bucket, its SSL-only policy, the replication IAM role, and
# the replication configuration used to be hand-rolled here. They are now
# provisioned by the `backup_bucket` module (s3.tf) via its
# `replication_region` input.
#
# Only the replica bucket needs to be adopted into the module: it holds
# the backup data, and recreating it would either collide on the bucket
# name or fail on a non-empty production bucket. Every other replication
# resource (versioning, encryption, public-access block, IAM role/policy,
# replication config) is ephemeral and is fine to destroy and recreate.

moved {
  from = aws_s3_bucket.replica
  to   = module.backup_bucket.aws_s3_bucket.replica[0]
}
