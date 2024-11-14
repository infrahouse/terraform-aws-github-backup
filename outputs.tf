output "instance_role_arn" {
  description = "ARN of the GitHub Backup instance role."
  value       = module.instance_profile.instance_role_arn
}
