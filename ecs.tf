resource "aws_ecs_cluster" "backup" {
  name = var.service_name

  # Container Insights gives per-task CPU/memory/network metrics in
  # CloudWatch, which is essential for spotting tasks that are close
  # to resource limits or running longer than expected.
  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.all_tags
}

resource "aws_ecs_task_definition" "backup" {
  family                   = var.service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.task_cpu
  memory                   = local.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  ephemeral_storage {
    size_in_gib = local.task_ephemeral_storage_gb
  }

  container_definitions = jsonencode([
    {
      name      = "github-backup"
      image     = var.image_uri
      essential = true

      environment = [
        {
          name  = "GITHUB_APP_ID"
          value = var.github_app_id
        },
        {
          name  = "GITHUB_APP_INSTALLATION_ID"
          value = var.github_app_installation_id
        },
        {
          name  = "GITHUB_APP_KEY_SECRET_ARN"
          value = module.github_app_key.secret_arn
        },
        {
          name  = "S3_BUCKET"
          value = module.backup_bucket.bucket_name
        },
        {
          name  = "AWS_DEFAULT_REGION"
          value = data.aws_region.current.name
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backup.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = local.all_tags
}
