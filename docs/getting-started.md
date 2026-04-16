# Getting Started

This guide walks you through deploying `terraform-aws-github-backup` for the first time.

## Prerequisites

Before you begin, ensure you have:

1. **Terraform >= 1.5** installed
2. **AWS provider ~> 6.0** — the module uses provider v6 per-resource `region` arguments for the
   cross-region replica bucket
3. **AWS credentials** configured with permissions for:
    - ECS (cluster, task definition)
    - EventBridge (rule, target)
    - S3 (primary bucket, replica bucket, replication configuration)
    - IAM (roles, policies)
    - Secrets Manager (secret, resource policy)
    - CloudWatch (log groups, alarms)
    - SNS (topic, subscriptions)
4. **Existing infrastructure:**
    - A VPC with subnets that have outbound internet access (NAT gateway or public subnets). The
      Fargate task needs to reach GitHub and the AWS S3/Secrets Manager endpoints.
5. **A GitHub App** installed on your organization (created in the next step)

## Step 1: Create a GitHub App

1. Go to **GitHub organization → Settings → Developer settings → GitHub Apps → New GitHub App**
2. Set the following permissions (read-only is sufficient):
    - **Repository permissions → Contents**: Read-only
    - **Repository permissions → Metadata**: Read-only
3. Install the App on your organization (select all repositories, or a subset)
4. Note the **App ID** (visible on the App settings page)
5. Note the **Installation ID** (the numeric suffix in the installation URL:
   `https://github.com/organizations/YOUR_ORG/settings/installations/INSTALLATION_ID`)
6. On the App settings page, click **Generate a private key**. Save the downloaded `.pem` file
   securely — you'll upload it to Secrets Manager in Step 3.

## Step 2: Deploy the Module

Create a Terraform configuration:

```hcl
terraform {
  required_version = "~> 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-west-2"

  default_tags {
    tags = {
      created_by  = "your-org/infra-repo"
      environment = "production"
    }
  }
}

module "github_backup" {
  source  = "registry.infrahouse.com/infrahouse/github-backup/aws"
  version = "2.0.1"

  github_app_id              = "123456"
  github_app_installation_id = "78901234"

  alarm_emails                  = ["devops@example.com"]
  github_app_key_secret_writers = [aws_iam_role.deployer.arn]
  replica_region                = "us-east-1"
  subnets                       = ["subnet-abc123", "subnet-def456"]

  # Optional
  schedule_expression   = "rate(1 day)"
  backup_retention_days = 365
}
```

Apply it:

```bash
terraform init
terraform apply
```

## Step 3: Store the GitHub App Private Key

The module creates a Secrets Manager secret for the GitHub App PEM. Until you populate it, the ECS
task cannot authenticate to GitHub and every run will fail.

Write the PEM into the secret from a role listed in `github_app_key_secret_writers`:

```bash
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw github_app_key_secret_arn)" \
  --secret-string file://github-app.pem
```

The role(s) in `github_app_key_secret_writers` must be used for this operation. The Terraform
caller role automatically gets admin access to the secret.

## Step 4: Verify the First Backup

By default the schedule is `rate(1 day)`. You can trigger the task manually to verify without
waiting:

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
TASK_DEF=$(terraform output -raw task_definition_arn)
SUBNETS='["subnet-abc123","subnet-def456"]'
SG=$(terraform output -raw security_group_id)

aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=${SUBNETS},securityGroups=[\"$SG\"],assignPublicIp=DISABLED}"
```

Watch the logs:

```bash
aws logs tail "$(terraform output -raw log_group_name)" --follow
```

On success the S3 primary bucket will contain:

```
github-backup/
  2026-04-16/
    manifest.json
    your-org/
      repo-a.bundle
      repo-b.bundle
```

Cross-region replication happens asynchronously; objects will appear in the replica bucket shortly
after.

## Confirm the SNS Subscription

AWS sends a confirmation email to every address in `alarm_emails`. Until each subscriber clicks the
confirmation link, alarms will not be delivered. This is a one-time step per address.

## Next Steps

- [Configuration](configuration.md) — tune the schedule, retention, resource sizes
- [Architecture](architecture.md) — understand what each component does and why
- [Troubleshooting](troubleshooting.md) — restore procedures and common failures
