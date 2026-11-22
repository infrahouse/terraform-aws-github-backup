# Upgrading

This page covers upgrades that need more than a version bump. The examples assume the module block is
named `github_backup` and the cluster uses the default `service_name`, `github-backup`. Substitute your own.

## From 2.0.1 or 2.0.2

Upgrade to 2.0.4 or later. Skip 2.0.3 (see [below](#if-you-already-upgraded-to-203)).

Since 2.0.3, the [s3-bucket module](https://registry.terraform.io/modules/infrahouse/s3-bucket/aws/latest)
manages the replica bucket, its settings and the replication configuration. Before that, this module defined them
itself. 2.0.4 adds `moved` blocks, so Terraform adopts the existing bucket settings at their new addresses instead
of destroying and recreating them. The replication IAM role and its policy stay in this module, so the upgrade
leaves them as they are.

### What the plan should show

**S3 settings move and update in place.** The plan reports each of these as moved, with an in-place update or no
change:

| 2.0.1 / 2.0.2 address | New address |
|---|---|
| `aws_s3_bucket.replica` | `module.backup_bucket.aws_s3_bucket.replica[0]` |
| `aws_s3_bucket_versioning.replica` | `module.backup_bucket.aws_s3_bucket_versioning.replica[0]` |
| `aws_s3_bucket_public_access_block.replica` | `module.backup_bucket.aws_s3_bucket_public_access_block.replica[0]` |
| `aws_s3_bucket_server_side_encryption_configuration.replica` | `module.backup_bucket.aws_s3_bucket_server_side_encryption_configuration.replica[0]` |
| `aws_s3_bucket_replication_configuration.backup` | `module.backup_bucket.aws_s3_bucket_replication_configuration.this[0]` |
| `aws_s3_bucket_lifecycle_configuration.backup` | `aws_s3_bucket_lifecycle_configuration.backup["source"]` |
| `aws_s3_bucket_lifecycle_configuration.replica` | `aws_s3_bucket_lifecycle_configuration.backup["replica"]` |

All addresses are inside your module block, for example `module.github_backup.aws_s3_bucket_versioning.replica`.
The in-place updates you should see:

- The replication configuration keeps its role. Its rule ID changes to `replicate-all` and the destination storage
  class from `STANDARD` to `STANDARD_IA`, as set by the s3-bucket module.
- From 2.0.1, both lifecycle configurations gain the `abort-incomplete-multipart-uploads` rule added in 2.0.2.
- Tags change, for example `module_version` on the source and replica buckets.

**The replication role and its policy don't change.** `aws_iam_role.replication` and
`aws_iam_role_policy.replication` keep their addresses and names. The s3-bucket module replicates with this role
instead of creating its own: a new role would mean deleting the old one, and Terraform would delete it before it
moved replication off it. Objects written in between would never reach the replica.

**A few resources are created**, among them an SSL-only bucket policy on the replica. On 2.0.1 the plan also creates
the Container Insights log group; see the next section.

**Nothing is destroyed.**

!!! danger "Stop if the plan destroys anything"
    If the plan destroys any resource, don't apply it. Check that you are on 2.0.4 or later, and
    [open an issue](https://github.com/infrahouse/terraform-aws-github-backup/issues) with the plan output.

### Container Insights log group

2.0.2 added `aws_cloudwatch_log_group.container_insights` to set a retention on the Container Insights log group
`/aws/ecs/containerinsights/<cluster name>/performance`. On a cluster that has been running, ECS has already
created that group, so the apply fails with `ResourceAlreadyExistsException`. This affects upgrades from 2.0.1, and
from 2.0.2 if its apply failed with the same error.

A module can't import the group for you: Terraform allows `import` blocks only in the root module. Add this to your
root module before you apply:

```hcl
import {
  to = module.github_backup.aws_cloudwatch_log_group.container_insights
  id = "/aws/ecs/containerinsights/github-backup/performance"
}
```

The cluster name is the module's `ecs_cluster_name` output, which equals `service_name`. To check whether the group
exists:

```bash
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/ecs/containerinsights/github-backup/performance"
```

Don't add the block if the group doesn't exist: an import of a missing object fails the plan.

With the block in place, the plan imports the group and updates it in place to `log_retention_days` and the
module's tags. ECS doesn't create it with that retention: on one production cluster it had 1-day retention, so
older performance logs are already gone. After the apply, you can remove the `import` block.

## If you already upgraded to 2.0.3

2.0.3 is missing the `moved` blocks. Its apply destroyed each S3 setting at the old address while it created the
same setting at the new address, and Terraform runs the two at the same time. When the destroy finished last, it
removed the setting from the bucket while Terraform state still lists it.

Upgrade to 2.0.4 or later and run `terraform plan`. The `moved` blocks for the S3 settings don't apply to you,
because your state already uses the new addresses.

**The replication role and its policy are replaced.** 2.0.3 replicated with a role the s3-bucket module created.
2.0.4 moves that role and its policy to `aws_iam_role.replication` and `aws_iam_role_policy.replication`. Their
names change, so the plan replaces both (`+/-`, create before destroy): Terraform creates the new role and policy,
moves replication to the new role, and only then deletes the old ones. The plan destroys nothing else.

**Restore any setting the 2.0.3 apply lost.** Look for these changes:

| Plan wants to | Setting lost in the race |
|---|---|
| create `module.backup_bucket.aws_s3_bucket_replication_configuration.this[0]` | Replication on the source bucket |
| create `module.backup_bucket.aws_s3_bucket_public_access_block.replica[0]` | Public access block on the replica |
| create `aws_s3_bucket_lifecycle_configuration.backup["source"]` or `["replica"]` | Expiration rules on that bucket |
| update `module.backup_bucket.aws_s3_bucket_versioning.replica[0]` from `Suspended` to `Enabled` | Versioning on the replica |

Versioning shows up as an update, not a create: destroying it suspends versioning rather than removing the
setting. If the plan shows none of these, nothing was lost. If it shows any, apply it to restore the setting.

The encryption configuration doesn't need checking: both resources set `AES256`, which is also the S3 default.

What a lost setting meant until you apply:

- **No replication, or replica versioning suspended:** new backups didn't reach the replica, and S3 doesn't
  replicate them retroactively. Each backup run uploads a full set of bundles, so the first run after the apply
  puts a complete, current backup in the replica. Backups from the runs in between exist only in the source
  bucket.
- **No public access block on the replica:** the replica relied on account-level public access settings only.
- **No lifecycle rules:** old backups didn't expire. Once restored, the rules apply to existing objects too.
