# terraform-aws-github-backup

This module automates the deployment of infrastructure for
the [InfraHouse GitHub Backup](https://github.com/apps/infrahouse-github-backup) application,
which is designed to back up GitHub repositories.

The instances within the Auto Scaling Group perform the following tasks:
- Read app installations and their configurations.
- Create an in-memory backup copy of the repositories.
- Upload the backups to an S3 bucket specified in the installation configuration.

**Note:** The backup of a repository is stored on an ephemeral disk,
meaning it is not retained after the instance is terminated. This design choice enhances safety and security.

On the client side, the backups are configured by
the [github-backup-configuration](https://github.com/infrahouse/terraform-aws-github-backup-configuration)
module.

## Usage

```hcl
module "terraform-aws-github-backup" {
  source  = "registry.infrahouse.com/infrahouse/github-backup/aws"
  version = "0.6.4"

  app_key_secret           = module.infrahouse-github-backup-app-key.secret_name
  subnets                  = module.management.subnet_private_ids
  instance_type            = "t3a.small"
  environment              = var.environment
  root_volume_size         = 60
  smtp_credentials_secret = module.smtp_credentials.secret_name
}
```
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | ~> 1.5 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 5.11 |
| <a name="requirement_random"></a> [random](#requirement\_random) | ~> 3.6 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | ~> 5.11 |
| <a name="provider_random"></a> [random](#provider\_random) | ~> 3.6 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_instance_profile"></a> [instance\_profile](#module\_instance\_profile) | registry.infrahouse.com/infrahouse/instance-profile/aws | 1.5.1 |
| <a name="module_userdata"></a> [userdata](#module\_userdata) | registry.infrahouse.com/infrahouse/cloud-init/aws | 1.12.4 |

## Resources

| Name | Type |
|------|------|
| [aws_autoscaling_group.main](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/autoscaling_group) | resource |
| [aws_launch_template.github-backup](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/launch_template) | resource |
| [aws_security_group.backend](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group) | resource |
| [aws_vpc_security_group_egress_rule.backend_outgoing](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_egress_rule) | resource |
| [aws_vpc_security_group_ingress_rule.backend_icmp](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_ingress_rule) | resource |
| [aws_vpc_security_group_ingress_rule.backend_ssh_local](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_ingress_rule) | resource |
| [random_string.profile_suffix](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/string) | resource |
| [aws_ami.selected](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ami) | data source |
| [aws_ami.ubuntu_22](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ami) | data source |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_default_tags.provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/default_tags) | data source |
| [aws_iam_policy_document.default_permissions](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |
| [aws_secretsmanager_secret.app_key_secret](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/secretsmanager_secret) | data source |
| [aws_subnet.selected](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/subnet) | data source |
| [aws_vpc.service](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/vpc) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_ami"></a> [ami](#input\_ami) | Image for EC2 instances | `string` | `null` | no |
| <a name="input_app_key_secret"></a> [app\_key\_secret](#input\_app\_key\_secret) | secret name where the GitHub PEM is stored. | `string` | n/a | yes |
| <a name="input_asg_max_healthy_percentage"></a> [asg\_max\_healthy\_percentage](#input\_asg\_max\_healthy\_percentage) | Specifies the upper limit on the number of instances that are in the InService or Pending state with a healthy status during an instance replacement activity. | `number` | `100` | no |
| <a name="input_asg_max_size"></a> [asg\_max\_size](#input\_asg\_max\_size) | Maximum number of instances in ASG | `number` | `1` | no |
| <a name="input_asg_min_healthy_percentage"></a> [asg\_min\_healthy\_percentage](#input\_asg\_min\_healthy\_percentage) | Specifies the lower limit on the number of instances that must be in the InService state with a healthy status during an instance replacement activity. | `number` | `0` | no |
| <a name="input_asg_min_size"></a> [asg\_min\_size](#input\_asg\_min\_size) | Minimum number of instances in ASG | `number` | `1` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | Name of environment | `string` | `"development"` | no |
| <a name="input_instance_role_name"></a> [instance\_role\_name](#input\_instance\_role\_name) | If specified, the instance profile role will have this name. Otherwise, the role name will be generated. | `string` | `"infrahouse-github-backup"` | no |
| <a name="input_instance_type"></a> [instance\_type](#input\_instance\_type) | EC2 instances type | `string` | `"t3.micro"` | no |
| <a name="input_key_pair_name"></a> [key\_pair\_name](#input\_key\_pair\_name) | SSH keypair name to be deployed in EC2 instances | `string` | n/a | yes |
| <a name="input_max_instance_lifetime_days"></a> [max\_instance\_lifetime\_days](#input\_max\_instance\_lifetime\_days) | The maximum amount of time, in \_days\_, that an instance can be in service, values must be either equal to 0 or between 7 and 365 days. | `number` | `30` | no |
| <a name="input_root_volume_size"></a> [root\_volume\_size](#input\_root\_volume\_size) | Root volume size in EC2 instance in Gigabytes | `number` | `30` | no |
| <a name="input_service_name"></a> [service\_name](#input\_service\_name) | Descriptive name of a service that will use this VPC | `string` | `"infrahouse-github-backup"` | no |
| <a name="input_subnets"></a> [subnets](#input\_subnets) | Subnet ids where EC2 instances should be present | `list(string)` | n/a | yes |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to apply to instances in the autoscaling group. | `map(string)` | <pre>{<br/>  "Name": "infrahouse-github-backup"<br/>}</pre> | no |

## Outputs

No outputs.
