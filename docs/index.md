# terraform-aws-github-backup

A Terraform module that backs up all repositories in a GitHub organization to S3
using an ECS Fargate scheduled task.

## Overview

This module deploys a scheduled ECS Fargate task that:

1. Authenticates to GitHub using a customer-owned GitHub App
2. Lists all repositories accessible to the App installation
3. Creates a `git bundle` (full mirror) of each repository
4. Uploads the bundles to a versioned S3 bucket
5. Writes a manifest and publishes CloudWatch metrics

## Architecture

```
EventBridge Schedule (e.g. daily 2am)
       |
       v
ECS Fargate Task
  1. Read GitHub App private key from Secrets Manager
  2. Generate JWT, exchange for installation token
  3. List all repos via GitHub API
  4. git clone --mirror each repo
  5. git bundle create
  6. Upload bundles to S3
  7. Report success/failure metrics to CloudWatch

S3 Bucket (versioned, lifecycle policies)
  github-backup/
    2026-02-10/
      manifest.json
      org-name/
        repo-a.bundle
        repo-b.bundle

S3 Replica Bucket (cross-region)
  Replicates all objects for disaster recovery
```

## Getting Started

### Prerequisites

- Terraform >= 1.5
- AWS provider >= 6.0
- A GitHub App installed on your organization with read-only repository access

### 1. Create a GitHub App

1. Go to your GitHub organization **Settings > Developer settings > GitHub Apps > New GitHub App**
2. Set the following permissions:
    - **Repository permissions > Contents**: Read-only
    - **Repository permissions > Metadata**: Read-only
3. Install the App on your organization
4. Note the **App ID** (from App settings) and **Installation ID** (from the installation URL)
5. Generate a private key (PEM file) and save it securely

### 2. Deploy the Module

```hcl
module "github_backup" {
  source  = "registry.infrahouse.com/infrahouse/github-backup/aws"
  version = "~> 1.0"

  github_app_id              = "123456"
  github_app_installation_id = "78901234"

  alarm_emails                  = ["devops@example.com"]
  github_app_key_secret_writers = [aws_iam_role.deployer.arn]
  replica_region                = "us-east-1"
  subnets                       = ["subnet-abc123", "subnet-def456"]
}
```

### 3. Store the App Private Key

The module creates a Secrets Manager secret for the GitHub App private key.
After deployment, write the PEM key into the secret:

```bash
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw github_app_key_secret_arn)" \
  --secret-string file://github-app.pem
```

The role(s) specified in `github_app_key_secret_writers` must be used for this
operation. The Terraform caller role automatically gets admin access to the
secret.

## Configuration

### Required Variables

| Variable | Type | Description |
|---|---|---|
| `github_app_id` | `string` | The GitHub App ID. Found in the App's settings page. |
| `github_app_installation_id` | `string` | The installation ID of the GitHub App on the target organization. |
| `alarm_emails` | `list(string)` | Email addresses to receive CloudWatch alarm notifications. At least one required. |
| `replica_region` | `string` | AWS region for cross-region backup replication. |
| `github_app_key_secret_writers` | `list(string)` | IAM role ARNs allowed to write the GitHub App private key into the secret. At least one required. |
| `subnets` | `list(string)` | Subnet IDs for the Fargate task. Must have internet access. |

### Optional Variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `environment` | `string` | `"development"` | Name of environment. Lowercase, numbers, and underscores only. |
| `service_name` | `string` | `"github-backup"` | Descriptive name for the service. Used for naming resources. |
| `schedule_expression` | `string` | `"rate(1 day)"` | EventBridge schedule expression for backup frequency. |
| `backup_retention_days` | `number` | `365` | Days to retain backups in S3. Set to 0 to disable expiration. |
| `image_uri` | `string` | `"public.ecr.aws/infrahouse/github-backup:latest"` | Docker image URI for the backup runner. |
| `s3_bucket_name` | `string` | `null` | Custom name for the S3 backup bucket. Auto-generated if null. |
| `force_destroy` | `bool` | `false` | Allow destroying S3 buckets with objects. For testing only. |
| `tags` | `map(string)` | `{}` | Tags to apply to all resources. |

### Outputs

| Output | Description |
|---|---|
| `s3_bucket_name` | Name of the S3 bucket where backups are stored. |
| `s3_bucket_arn` | ARN of the S3 bucket where backups are stored. |
| `github_app_key_secret_arn` | ARN of the Secrets Manager secret for the GitHub App private key. |
| `ecs_cluster_arn` | ARN of the ECS cluster. |
| `ecs_cluster_name` | Name of the ECS cluster. |
| `task_definition_arn` | ARN of the ECS task definition. |
| `task_role_arn` | ARN of the IAM role used by the backup task. |
| `log_group_name` | Name of the CloudWatch log group. |
| `schedule_rule_arn` | ARN of the EventBridge schedule rule. |
| `security_group_id` | ID of the security group for the Fargate task. |

## Key Design Decisions

- **Fargate** -- no always-on compute, no Lambda timeout limits
- **Customer-owned GitHub App** -- no shared credentials, short-lived tokens
- **InfraHouse-published container image** on public ECR
- **S3 with versioning** and lifecycle policies for retention
- **Cross-region replication** for disaster recovery
- **AWS provider v6** -- per-resource `region` attribute, no aliased providers
- **Module-managed secret** -- the module creates and manages the Secrets Manager
  secret with a fine-grained resource policy (admin/writers/readers separation)

## Disaster Recovery

### RPO and RTO

| Metric | Value | Notes |
|---|---|---|
| **RPO** (Recovery Point Objective) | Up to the schedule interval (default: 24h) | Determined by `schedule_expression`. Worst case is one full interval of data loss. |
| **RTO** (Recovery Time Objective) | Minutes per repository | Restoring a single repo from a bundle takes seconds. Full org restore depends on the number and size of repositories. |

### Backup Storage

Backups are stored in two locations:

- **Primary bucket** -- in the region where the module is deployed
- **Replica bucket** -- in `replica_region`, automatically synchronized via S3 cross-region replication

Both buckets are versioned, so even if a backup is overwritten or deleted, previous versions are retained according to the lifecycle policy.

### Restore Procedures

Git bundles are portable and self-contained. Each bundle is a full mirror of the repository at the time of backup, including all branches, tags, and history.

#### Restore a single repository

```bash
# Download the bundle from S3
aws s3 cp s3://BUCKET/github-backup/2026-02-10/org-name/repo.bundle repo.bundle

# Verify the bundle is valid
git bundle verify repo.bundle

# Clone from the bundle
git clone repo.bundle repo-restored

# Point the restored repo back to GitHub
cd repo-restored
git remote set-url origin git@github.com:org-name/repo.git
git push --mirror origin
```

#### Restore from the replica region

If the primary region is unavailable:

```bash
# Download from the replica bucket
aws s3 cp s3://BUCKET-replica/github-backup/2026-02-10/org-name/repo.bundle repo.bundle \
  --region REPLICA_REGION

# Then follow the same restore steps above
```

#### Restore all repositories from a specific date

```bash
# List available backup dates
aws s3 ls s3://BUCKET/github-backup/

# Download all bundles for a specific date
aws s3 cp s3://BUCKET/github-backup/2026-02-10/ ./restore/ --recursive

# Check the manifest for details
cat restore/manifest.json

# Restore each bundle
for bundle in restore/org-name/*.bundle; do
  repo_name=$(basename "$bundle" .bundle)
  git clone "$bundle" "restored/$repo_name"
done
```

#### Add a bundle as a remote to an existing repo

```bash
git remote add backup repo.bundle
git fetch backup
```

### Failure Scenarios

| Scenario | Detection | Recovery |
|---|---|---|
| Single repo fails to back up | `backup-failure` CloudWatch alarm | Check logs, re-run task manually |
| Task does not run | `task-not-running` CloudWatch alarm | Check EventBridge rule and ECS cluster |
| Primary bucket unavailable | AWS region outage | Restore from replica bucket |
| GitHub App key compromised | Revoke in GitHub App settings | Generate new key, update the Secrets Manager secret |
| Backup corruption | Future: verification task ([#21](https://github.com/infrahouse/terraform-aws-github-backup/issues/21)) | Restore from a previous day's backup (S3 versioning) |

## Requirements

| Name | Version |
|---|---|
| terraform | ~> 1.5 |
| aws | ~> 6.0 |
