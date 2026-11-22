resource "aws_cloudwatch_log_group" "backup" {
  name              = "/ecs/${var.service_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.log_group_kms_key_arn
  tags              = local.all_tags
}

# ECS Container Insights auto-creates this log group if we don't
# pre-create it, with a retention ECS picks rather than ours (a production
# cluster on 2.0.1 got 1-day retention). Managing it here ensures the
# performance logs honor var.log_retention_days (ISO27001 requirement).
# On a cluster deployed before 2.0.2 the group already exists, and the
# caller must import it in their root module; see docs/upgrading.md.
# Reference the cluster's .name attribute (not var.service_name) so this
# log group stays tied to the cluster if its naming scheme ever changes.
resource "aws_cloudwatch_log_group" "container_insights" {
  name              = "/aws/ecs/containerinsights/${aws_ecs_cluster.backup.name}/performance"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.log_group_kms_key_arn
  tags              = local.all_tags
}

# Alarm: one or more repositories failed to back up.
# The backup script publishes BackupFailure as a count of
# repos that could not be cloned/bundled/uploaded.
resource "aws_cloudwatch_metric_alarm" "backup_failure" {
  alarm_name        = "${var.service_name}-backup-failure"
  alarm_description = <<-EOT
    One or more GitHub repositories failed to back up.
    Check the CloudWatch log group /ecs/${var.service_name}
    for details.
  EOT

  namespace   = "GitHubBackup"
  metric_name = "BackupFailure"
  statistic   = "Sum"

  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  period              = 86400 # 24 hours
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]

  tags = local.all_tags
}

# Alarm: the backup task did not run at all in the expected
# window.  If no BackupSuccess metric is published the task
# either was not scheduled, failed to start, or crashed
# before publishing metrics.
resource "aws_cloudwatch_metric_alarm" "task_not_running" {
  alarm_name        = "${var.service_name}-task-not-running"
  alarm_description = <<-EOT
    GitHub backup task has not run in the last 24 hours.
    Verify the EventBridge schedule and check ECS task
    status in the ${var.service_name} cluster.
  EOT

  namespace   = "GitHubBackup"
  metric_name = "BackupSuccess"
  statistic   = "SampleCount"

  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = 1
  period              = 86400 # 24 hours
  treat_missing_data  = "breaching"

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]

  tags = local.all_tags
}
