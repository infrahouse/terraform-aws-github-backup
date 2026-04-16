output "github_app_key_secret_arn" {
  description = "ARN of the Secrets Manager secret that must be populated with the GitHub App PEM."
  value       = module.github_backup.github_app_key_secret_arn
}

output "s3_bucket_name" {
  description = "Primary S3 bucket where daily backups are uploaded."
  value       = module.github_backup.s3_bucket_name
}

output "replica_bucket_name" {
  description = "Cross-region replica S3 bucket."
  value       = module.github_backup.replica_bucket_name
}

output "ecs_cluster_name" {
  description = "Name of the ECS Fargate cluster running the scheduled backup task."
  value       = module.github_backup.ecs_cluster_name
}

output "log_group_name" {
  description = "CloudWatch log group receiving task stdout."
  value       = module.github_backup.log_group_name
}
