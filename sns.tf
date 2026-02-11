resource "aws_sns_topic" "alarms" {
  name              = "${var.service_name}-alarms"
  display_name      = "GitHub Backup Alarms"
  kms_master_key_id = "alias/aws/sns"
  tags              = local.all_tags
}

resource "aws_sns_topic_subscription" "alarm_emails" {
  for_each = toset(var.alarm_emails)

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = each.value
}