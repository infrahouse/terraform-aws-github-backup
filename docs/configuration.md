# Configuration Reference

This page documents all configuration variables for the `terraform-aws-github-backup` module.

## Required Variables

These variables must be provided — they have no defaults.

### `github_app_id`

The GitHub App ID, visible on the App's settings page in GitHub.

```hcl
github_app_id = "123456"
```

### `github_app_installation_id`

Installation ID of the GitHub App on the target organization. Found in the installation URL
(`https://github.com/organizations/YOUR_ORG/settings/installations/<ID>`).

```hcl
github_app_installation_id = "78901234"
```

### `alarm_emails`

Email addresses to receive CloudWatch alarm notifications. At least one is required. AWS sends a
confirmation email to each address — the subscription is inactive until confirmed.

```hcl
alarm_emails = ["devops@example.com", "oncall@example.com"]
```

### `replica_region`

AWS region for the cross-region S3 replica bucket. Must differ from the primary deployment region.

```hcl
replica_region = "us-east-1"
```

### `github_app_key_secret_writers`

List of IAM role ARNs allowed to write the GitHub App PEM into the Secrets Manager secret. At
least one is required — without a writer, nobody can populate the secret after deployment.

```hcl
github_app_key_secret_writers = [
  aws_iam_role.deployer.arn,
  "arn:aws:iam::123456789012:role/CI",
]
```

### `subnets`

Subnet IDs where the Fargate task runs. Must have outbound internet access (NAT gateway or public
subnets). Public IP assignment is detected automatically from the subnet's
`map_public_ip_on_launch` attribute.

```hcl
subnets = ["subnet-abc123", "subnet-def456"]
```

## Optional Variables

### `environment`

Environment name. Lowercase letters, numbers, and underscores only (no hyphens).

```hcl
environment = "production"  # default: "development"
```

### `service_name`

Used for naming the ECS cluster, log groups, and other resources. Lowercase alphanumeric with
hyphens.

```hcl
service_name = "github-backup"  # default: "github-backup"
```

### `schedule_expression`

EventBridge schedule expression. Must start with `rate(` or `cron(`.

```hcl
schedule_expression = "rate(1 day)"          # default: daily
schedule_expression = "cron(0 2 * * ? *)"    # daily at 02:00 UTC
schedule_expression = "rate(12 hours)"       # twice a day
```

### `backup_retention_days`

Days to retain backups in S3 before lifecycle expiration. Set to `0` to disable expiration (keep
forever).

```hcl
backup_retention_days = 365   # default
backup_retention_days = 0     # keep backups indefinitely
```

### `image_uri`

Docker image URI for the backup runner. Defaults to the InfraHouse public ECR image at `latest`.

!!! warning "Pin to a SHA in production"
    `:latest` is convenient for getting started but exposes you to breaking changes pushed to
    the tag and to supply-chain compromise of that tag. In production, always pin to a specific
    commit SHA tag so image changes land through a deliberate Terraform apply, not a surprise
    pull on the next scheduled task.

```hcl
image_uri = "public.ecr.aws/infrahouse/github-backup:latest"  # default (getting-started only)
image_uri = "public.ecr.aws/infrahouse/github-backup:abc1234" # production: pin to SHA
```

### `s3_bucket_name`

Custom name for the S3 primary bucket. If `null` (default), the name is auto-generated as
`<service_name>-<account_id>-<region>`.

```hcl
s3_bucket_name = "my-org-github-backups"  # default: null (auto)
```

### `log_retention_days`

Days to retain CloudWatch logs. Applies to both `/ecs/<service_name>` and the Container Insights
performance log group.

```hcl
log_retention_days = 365  # default (matches ISO 27001 log retention)
```

### `log_group_kms_key_arn`

KMS key ARN to encrypt CloudWatch log groups. If `null` (default), logs use AWS-managed keys.

```hcl
log_group_kms_key_arn = aws_kms_key.logs.arn  # default: null
```

### `task_cpu`

Fargate task CPU (1024 = 1 vCPU). Must be a Fargate-supported combination with `task_memory`.

```hcl
task_cpu = 1024  # default
```

### `task_memory`

Fargate task memory in MiB.

```hcl
task_memory = 2048  # default
```

### `task_ephemeral_storage_gb`

Ephemeral storage (GiB) attached to the Fargate task. Must hold the biggest single repo mirror
**and** its git bundle simultaneously. For orgs with large repos, raise this.

```hcl
task_ephemeral_storage_gb = 50   # default
task_ephemeral_storage_gb = 200  # org has large monorepos
```

### `force_destroy`

Allow `terraform destroy` to delete S3 buckets that still contain objects. Only set to `true` for
ephemeral test environments.

```hcl
force_destroy = false  # default
```

### `tags`

Extra tags merged into the module's default tag set. Applied to all resources.

```hcl
tags = {
  cost_center = "platform"
  owner       = "sre"
}
```

## Outputs

| Output | Description |
|--------|-------------|
| `s3_bucket_name` | Name of the primary S3 bucket where backups are stored. |
| `s3_bucket_arn` | ARN of the primary S3 bucket. |
| `replica_bucket_name` | Name of the replica S3 bucket in `replica_region`. |
| `replica_bucket_arn` | ARN of the replica S3 bucket. |
| `github_app_key_secret_arn` | ARN of the Secrets Manager secret for the GitHub App PEM. |
| `ecs_cluster_arn` | ARN of the ECS cluster. |
| `ecs_cluster_name` | Name of the ECS cluster. |
| `task_definition_arn` | ARN of the ECS task definition. |
| `task_role_arn` | IAM role the backup task assumes at runtime. |
| `log_group_name` | CloudWatch log group receiving task stdout. |
| `schedule_rule_arn` | ARN of the EventBridge schedule rule. |
| `security_group_id` | Security group attached to the Fargate task. |
