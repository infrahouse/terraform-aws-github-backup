locals {
  default_module_tags = {
    environment : var.environment
    service : var.service_name
    account : data.aws_caller_identity.current.account_id
    created_by_module : "infrahouse/github-backup/aws"
  }
  default_asg_tags = merge(
    {
      Name : "infrahouse-github-backup"
    },
    local.default_module_tags
  )
}
