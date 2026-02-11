module "github_app_key" {
  source             = "registry.infrahouse.com/infrahouse/secret/aws"
  version            = "~> 1.1"
  environment        = var.environment
  service_name       = var.service_name
  secret_description = "GitHub App private key (PEM) for ${var.service_name}"
  secret_name_prefix = "${var.service_name}-github-app-key"
  readers = [
    aws_iam_role.execution.arn,
    aws_iam_role.task.arn,
  ]
  writers = var.github_app_key_secret_writers
  tags    = local.all_tags
}