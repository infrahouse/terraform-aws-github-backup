resource "aws_cloudwatch_event_rule" "backup" {
  name_prefix         = "${var.service_name}-"
  description         = "Schedule for GitHub backup task"
  schedule_expression = var.schedule_expression
  tags                = local.all_tags
}

data "aws_iam_policy_document" "eventbridge_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "eventbridge" {
  name_prefix        = "${var.service_name}-events-"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume_role.json
  tags               = local.all_tags
}

data "aws_iam_policy_document" "eventbridge_permissions" {
  statement {
    actions = ["ecs:RunTask"]
    resources = [
      # Allow running any revision of this task definition
      replace(
        aws_ecs_task_definition.backup.arn,
        "/:\\d+$/",
        ":*"
      )
    ]
  }

  statement {
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.execution.arn,
      aws_iam_role.task.arn,
    ]
  }
}

resource "aws_iam_role_policy" "eventbridge" {
  name_prefix = "${var.service_name}-events-"
  role        = aws_iam_role.eventbridge.id
  policy      = data.aws_iam_policy_document.eventbridge_permissions.json
}

resource "aws_cloudwatch_event_target" "backup" {
  rule     = aws_cloudwatch_event_rule.backup.name
  arn      = aws_ecs_cluster.backup.arn
  role_arn = aws_iam_role.eventbridge.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.backup.arn
    task_count          = 1
    launch_type         = "FARGATE"

    network_configuration {
      subnets          = var.subnets
      security_groups  = [aws_security_group.backup.id]
      assign_public_ip = data.aws_subnet.selected.map_public_ip_on_launch
    }
  }
}
