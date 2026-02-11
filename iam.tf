# ── Task Execution Role (used by ECS agent) ─────────────────────

data "aws_iam_policy_document" "execution_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "execution" {
  name_prefix        = "${var.service_name}-exec-"
  assume_role_policy = data.aws_iam_policy_document.execution_assume_role.json
  tags               = local.all_tags
}

data "aws_iam_policy" "ecs_task_execution" {
  name = "AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = data.aws_iam_policy.ecs_task_execution.arn
}

# ── Task Role (used by the running container) ───────────────────

data "aws_iam_policy_document" "task_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "task" {
  name_prefix        = "${var.service_name}-task-"
  assume_role_policy = data.aws_iam_policy_document.task_assume_role.json
  tags               = local.all_tags
}

data "aws_iam_policy_document" "task_permissions" {
  # S3 — upload backups
  statement {
    actions = [
      "s3:PutObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      module.backup_bucket.bucket_arn,
      "${module.backup_bucket.bucket_arn}/*",
    ]
  }

  # Secrets Manager — read GitHub App private key
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [module.github_app_key.secret_arn]
  }

  # CloudWatch — publish backup metrics
  statement {
    actions = [
      "cloudwatch:PutMetricData",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["GitHubBackup"]
    }
  }

}

resource "aws_iam_role_policy" "task" {
  name_prefix = "${var.service_name}-task-"
  role        = aws_iam_role.task.id
  policy      = data.aws_iam_policy_document.task_permissions.json
}
