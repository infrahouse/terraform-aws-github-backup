locals {
  module_version = "0.7.3"

  default_module_tags = {
    environment : var.environment
    service : var.service_name
    account : data.aws_caller_identity.current.account_id
    created_by_module : "infrahouse/github-backup/aws"
  }
  default_asg_tags = merge(
    {
      Name : "infrahouse-github-backup"
      module_version : local.module_version
    },
    local.default_module_tags
  )
  ami_name_pattern_pro = "ubuntu-pro-server/images/hvm-ssd-gp3/ubuntu-${var.ubuntu_codename}-*"

}
