resource "aws_ecr_repository" "backup" {
  name         = "github-backup-test"
  force_delete = true

  tags = {
    Name = "github-backup-test"
  }
}

module "main" {
  source = "../../"

  github_app_id              = var.github_app_id
  github_app_installation_id = var.github_app_installation_id
  alarm_emails               = ["devops-test@infrahouse.com"]
  # Use ecs-tester as the writer role (distinct from the Terraform caller
  # role, github-backup-tester, which automatically gets admin access via
  # the secret module's caller_role logic).
  github_app_key_secret_writers = [data.aws_iam_role.ecs_tester.arn]
  replica_region                = "us-east-1"
  subnets                       = var.subnets
  environment                   = "development"
  force_destroy                 = true
  image_uri                     = "${aws_ecr_repository.backup.repository_url}:latest"
}