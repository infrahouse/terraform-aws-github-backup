output "s3_bucket_name" {
  value = module.main.s3_bucket_name
}

output "s3_bucket_arn" {
  value = module.main.s3_bucket_arn
}

output "github_app_key_secret_arn" {
  value = module.main.github_app_key_secret_arn
}

output "ecs_cluster_arn" {
  value = module.main.ecs_cluster_arn
}

output "task_definition_arn" {
  value = module.main.task_definition_arn
}

output "task_role_arn" {
  value = module.main.task_role_arn
}

output "log_group_name" {
  value = module.main.log_group_name
}

output "schedule_rule_arn" {
  value = module.main.schedule_rule_arn
}

output "ecs_cluster_name" {
  value = module.main.ecs_cluster_name
}

output "security_group_id" {
  value = module.main.security_group_id
}

output "account_id" {
  value = data.aws_caller_identity.this.account_id
}

output "ecr_repo_url" {
  value = aws_ecr_repository.backup.repository_url
}
