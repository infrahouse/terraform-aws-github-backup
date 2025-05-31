data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_default_tags" "provider" {}

data "aws_subnet" "selected" {
  id = var.subnets[0]
}

data "aws_vpc" "service" {
  id = data.aws_subnet.selected.vpc_id
}

data "aws_ami" "selected" {
  filter {
    name = "image-id"
    values = [
      var.ami == null ? data.aws_ami.ubuntu_22.id : var.ami
    ]
  }
}

data "aws_ami" "ubuntu_22" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}

data "aws_iam_policy_document" "default_permissions" {
  statement {
    actions = [
      "sts:GetCallerIdentity",
      "sts:AssumeRole"
    ]
    resources = [
      "*"
    ]
  }
  statement {
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [
      data.aws_secretsmanager_secret.app_key_secret.arn
    ]
  }
  # Allow reading tags by ih-ec2 tags
  # The "ec2:DescribeInstances" action doesn't support Conditions, so we have to use the wildcard
  statement {
    actions = [
      "ec2:DescribeInstances",
    ]
    resources = [
      "*"
    ]
  }
}

data "aws_secretsmanager_secret" "app_key_secret" {
  name = var.app_key_secret
}
