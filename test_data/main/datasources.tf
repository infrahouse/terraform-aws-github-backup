data "aws_caller_identity" "this" {}
data "aws_region" "current" {}

data "aws_iam_role" "ecs_tester" {
  name = "ecs-tester"
}
