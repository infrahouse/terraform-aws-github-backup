data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_default_tags" "provider" {}

data "aws_subnet" "selected" {
  id = var.subnets[0]
}
