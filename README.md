# terraform-aws-github-backup

[![Need Help?](https://img.shields.io/badge/Need%20Help%3F-Contact%20Us-0066CC)](https://infrahouse.com/contact)
[![Docs](https://img.shields.io/badge/docs-github.io-blue)](https://infrahouse.github.io/terraform-aws-github-backup/)
[![Registry](https://img.shields.io/badge/Terraform-Registry-purple?logo=terraform)](https://registry.terraform.io/modules/infrahouse/github-backup/aws/latest)
[![Release](https://img.shields.io/github/release/infrahouse/terraform-aws-github-backup.svg)](https://github.com/infrahouse/terraform-aws-github-backup/releases/latest)
[![Security](https://img.shields.io/github/actions/workflow/status/infrahouse/terraform-aws-github-backup/vuln-scanner-pr.yml?label=Security)](https://github.com/infrahouse/terraform-aws-github-backup/actions/workflows/vuln-scanner-pr.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

[![AWS ECS](https://img.shields.io/badge/AWS-ECS-orange?logo=amazonecs)](https://aws.amazon.com/ecs/)
[![AWS S3](https://img.shields.io/badge/AWS-S3-green?logo=amazons3)](https://aws.amazon.com/s3/)

A Terraform module that backs up all repositories in a GitHub organization to S3
using an ECS Fargate scheduled task. Designed to be deployed by the customer in
their own AWS account with zero operational dependency on InfraHouse.

## Why This Module?

- **No always-on compute** -- Fargate runs on a schedule, you only pay for backup time
- **No Lambda timeout limits** -- large organizations with many repos back up without issues
- **Customer-owned GitHub App** -- no shared credentials, short-lived tokens only
- **Cross-region replication** -- S3 replication for disaster recovery
- **Full git history** -- uses `git bundle` for complete, portable backups

## Features

- ECS Fargate scheduled task (EventBridge) for daily/custom-schedule backups
- S3 bucket with versioning and configurable retention lifecycle
- Cross-region S3 replication (AWS provider v6, no aliased providers)
- CloudWatch Logs, metrics, and alarm on backup failure
- Least-privilege IAM roles for task execution and task runtime
- Customer creates and owns their own GitHub App (read-only access)

## Quick Start

1. **Create a GitHub App** in your organization (see [Getting Started](https://infrahouse.github.io/terraform-aws-github-backup/#getting-started))
2. **Deploy the module** -- the module creates a Secrets Manager secret for the App private key:

```hcl
module "github_backup" {
  source  = "registry.infrahouse.com/infrahouse/github-backup/aws"
  version = "2.0.0"

  github_app_id              = "123456"
  github_app_installation_id = "78901234"

  alarm_emails                  = ["devops@example.com"]
  github_app_key_secret_writers = [aws_iam_role.deployer.arn]
  replica_region                = "us-east-1"
  subnets                       = ["subnet-abc123", "subnet-def456"]

  # Optional
  schedule_expression  = "rate(1 day)"
  backup_retention_days = 365
}
```

3. **Store the App private key** in the secret created by the module (output: `github_app_key_secret_arn`)

## Documentation

- [Getting Started](https://infrahouse.github.io/terraform-aws-github-backup/#getting-started)
- [Configuration](https://infrahouse.github.io/terraform-aws-github-backup/#configuration)
- [Architecture](https://infrahouse.github.io/terraform-aws-github-backup/#architecture)
- [Restoring from a Backup](https://infrahouse.github.io/terraform-aws-github-backup/#restoring-from-a-backup)

<!-- BEGIN_TF_DOCS -->

## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | ~> 1.5 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 6.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | ~> 6.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_backup_bucket"></a> [backup\_bucket](#module\_backup\_bucket) | registry.infrahouse.com/infrahouse/s3-bucket/aws | 0.3.1 |
| <a name="module_github_app_key"></a> [github\_app\_key](#module\_github\_app\_key) | registry.infrahouse.com/infrahouse/secret/aws | ~> 1.1 |

## Resources

| Name | Type |
|------|------|
| [aws_cloudwatch_event_rule.backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_rule) | resource |
| [aws_cloudwatch_event_target.backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_target) | resource |
| [aws_cloudwatch_log_group.backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_cloudwatch_metric_alarm.backup_failure](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_metric_alarm) | resource |
| [aws_cloudwatch_metric_alarm.task_not_running](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_metric_alarm) | resource |
| [aws_ecs_cluster.backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_cluster) | resource |
| [aws_ecs_task_definition.backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_task_definition) | resource |
| [aws_iam_role.eventbridge](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.execution](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.replication](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.task](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy.eventbridge](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.replication](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.task](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy_attachment.execution](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_s3_bucket.replica](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket) | resource |
| [aws_s3_bucket_lifecycle_configuration.backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_lifecycle_configuration) | resource |
| [aws_s3_bucket_lifecycle_configuration.replica](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_lifecycle_configuration) | resource |
| [aws_s3_bucket_public_access_block.replica](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_public_access_block) | resource |
| [aws_s3_bucket_replication_configuration.backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_replication_configuration) | resource |
| [aws_s3_bucket_server_side_encryption_configuration.replica](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_server_side_encryption_configuration) | resource |
| [aws_s3_bucket_versioning.replica](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_versioning) | resource |
| [aws_security_group.backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
| [aws_sns_topic.alarms](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic) | resource |
| [aws_sns_topic_subscription.alarm_emails](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic_subscription) | resource |
| [aws_vpc_security_group_egress_rule.all_outbound](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_egress_rule) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_default_tags.provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/default_tags) | data source |
| [aws_iam_policy.ecs_task_execution](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy) | data source |
| [aws_iam_policy_document.eventbridge_assume_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.eventbridge_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.execution_assume_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.replication_assume_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.replication_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.task_assume_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.task_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |
| [aws_subnet.selected](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/subnet) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_alarm_emails"></a> [alarm\_emails](#input\_alarm\_emails) | List of email addresses to receive CloudWatch alarm<br/>notifications. AWS will send confirmation emails that<br/>must be accepted. | `list(string)` | n/a | yes |
| <a name="input_backup_retention_days"></a> [backup\_retention\_days](#input\_backup\_retention\_days) | Number of days to retain backups in S3 before<br/>expiration. Set to 0 to disable expiration. | `number` | `365` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | Name of environment. | `string` | `"development"` | no |
| <a name="input_force_destroy"></a> [force\_destroy](#input\_force\_destroy) | Allow destroying S3 buckets even when they contain<br/>objects. Set to true only for testing. | `bool` | `false` | no |
| <a name="input_github_app_id"></a> [github\_app\_id](#input\_github\_app\_id) | The GitHub App ID. Found in the App's settings page. | `string` | n/a | yes |
| <a name="input_github_app_installation_id"></a> [github\_app\_installation\_id](#input\_github\_app\_installation\_id) | The installation ID of the GitHub App on<br/>the target organization. | `string` | n/a | yes |
| <a name="input_github_app_key_secret_writers"></a> [github\_app\_key\_secret\_writers](#input\_github\_app\_key\_secret\_writers) | List of IAM role ARNs that are allowed to write<br/>the GitHub App private key (PEM) into the secret<br/>created by this module. | `list(string)` | n/a | yes |
| <a name="input_image_uri"></a> [image\_uri](#input\_image\_uri) | Docker image URI for the backup runner.<br/>Defaults to the InfraHouse public ECR image tagged "latest".<br/>For production use, consider pinning to a specific commit SHA tag<br/>(e.g., "public.ecr.aws/infrahouse/github-backup:abc1234")<br/>to avoid unexpected changes. | `string` | `"public.ecr.aws/infrahouse/github-backup:latest"` | no |
| <a name="input_log_group_kms_key_arn"></a> [log\_group\_kms\_key\_arn](#input\_log\_group\_kms\_key\_arn) | ARN of a KMS key to encrypt the CloudWatch Log Group.<br/>If null, logs are encrypted with the default<br/>AWS-managed key. | `string` | `null` | no |
| <a name="input_log_retention_days"></a> [log\_retention\_days](#input\_log\_retention\_days) | Number of days to retain CloudWatch logs. | `number` | `365` | no |
| <a name="input_replica_region"></a> [replica\_region](#input\_replica\_region) | AWS region for cross-region backup replication. | `string` | n/a | yes |
| <a name="input_s3_bucket_name"></a> [s3\_bucket\_name](#input\_s3\_bucket\_name) | Name for the S3 backup bucket.<br/>If null, a name is auto-generated. | `string` | `null` | no |
| <a name="input_schedule_expression"></a> [schedule\_expression](#input\_schedule\_expression) | EventBridge schedule expression for backup frequency.<br/>Examples: "rate(1 day)", "cron(0 2 * * ? *)" | `string` | `"rate(1 day)"` | no |
| <a name="input_service_name"></a> [service\_name](#input\_service\_name) | Descriptive name of the service.<br/>Used for naming resources. | `string` | `"github-backup"` | no |
| <a name="input_subnets"></a> [subnets](#input\_subnets) | List of subnet IDs for the Fargate task.<br/>The subnets must have outbound internet access<br/>(GitHub API, S3, etc.) — either private subnets<br/>with a NAT gateway or public subnets.<br/>Public IP assignment is detected automatically<br/>from the subnet configuration. | `list(string)` | n/a | yes |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to apply to all resources. | `map(string)` | `{}` | no |
| <a name="input_task_cpu"></a> [task\_cpu](#input\_task\_cpu) | CPU units for the Fargate task (1024 = 1 vCPU). | `number` | `1024` | no |
| <a name="input_task_ephemeral_storage_gb"></a> [task\_ephemeral\_storage\_gb](#input\_task\_ephemeral\_storage\_gb) | Ephemeral storage (GiB) for the Fargate task.<br/>Must be large enough to hold the biggest single<br/>repository mirror and its git bundle simultaneously. | `number` | `50` | no |
| <a name="input_task_memory"></a> [task\_memory](#input\_task\_memory) | Memory (MiB) for the Fargate task. | `number` | `2048` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_ecs_cluster_arn"></a> [ecs\_cluster\_arn](#output\_ecs\_cluster\_arn) | ARN of the ECS cluster. |
| <a name="output_ecs_cluster_name"></a> [ecs\_cluster\_name](#output\_ecs\_cluster\_name) | Name of the ECS cluster. |
| <a name="output_github_app_key_secret_arn"></a> [github\_app\_key\_secret\_arn](#output\_github\_app\_key\_secret\_arn) | ARN of the Secrets Manager secret for the GitHub App private key. |
| <a name="output_log_group_name"></a> [log\_group\_name](#output\_log\_group\_name) | Name of the CloudWatch log group. |
| <a name="output_replica_bucket_arn"></a> [replica\_bucket\_arn](#output\_replica\_bucket\_arn) | ARN of the replica S3 bucket (cross-region). |
| <a name="output_replica_bucket_name"></a> [replica\_bucket\_name](#output\_replica\_bucket\_name) | Name of the replica S3 bucket (cross-region). |
| <a name="output_s3_bucket_arn"></a> [s3\_bucket\_arn](#output\_s3\_bucket\_arn) | ARN of the S3 bucket where backups are stored. |
| <a name="output_s3_bucket_name"></a> [s3\_bucket\_name](#output\_s3\_bucket\_name) | Name of the S3 bucket where backups are stored. |
| <a name="output_schedule_rule_arn"></a> [schedule\_rule\_arn](#output\_schedule\_rule\_arn) | ARN of the EventBridge schedule rule. |
| <a name="output_security_group_id"></a> [security\_group\_id](#output\_security\_group\_id) | ID of the security group for the Fargate task. |
| <a name="output_task_definition_arn"></a> [task\_definition\_arn](#output\_task\_definition\_arn) | ARN of the ECS task definition. |
| <a name="output_task_role_arn"></a> [task\_role\_arn](#output\_task\_role\_arn) | ARN of the IAM role used by the backup task. |
<!-- END_TF_DOCS -->

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[Apache 2.0](LICENSE)
