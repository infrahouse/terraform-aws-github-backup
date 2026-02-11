output "s3_bucket_name" {
  description = "Name of the S3 bucket where backups are stored."
  value       = module.backup_bucket.bucket_name
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket where backups are stored."
  value       = module.backup_bucket.bucket_arn
}

output "github_app_key_secret_arn" {
  description = "ARN of the Secrets Manager secret for the GitHub App private key."
  value       = module.github_app_key.secret_arn
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster."
  value       = aws_ecs_cluster.backup.arn
}

output "task_definition_arn" {
  description = "ARN of the ECS task definition."
  value       = aws_ecs_task_definition.backup.arn
}

output "task_role_arn" {
  description = "ARN of the IAM role used by the backup task."
  value       = aws_iam_role.task.arn
}

output "log_group_name" {
  description = "Name of the CloudWatch log group."
  value       = aws_cloudwatch_log_group.backup.name
}

output "schedule_rule_arn" {
  description = "ARN of the EventBridge schedule rule."
  value       = aws_cloudwatch_event_rule.backup.arn
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.backup.name
}

output "security_group_id" {
  description = "ID of the security group for the Fargate task."
  value       = aws_security_group.backup.id
}
