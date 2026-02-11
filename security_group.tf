resource "aws_security_group" "backup" {
  description = "Security group for ${var.service_name} Fargate task"
  name_prefix = "${var.service_name}-"
  vpc_id      = data.aws_subnet.selected.vpc_id

  tags = merge(
    {
      Name = "${var.service_name} fargate"
    },
    local.all_tags,
  )
}

# Fargate tasks only need outbound access to GitHub,
# S3, Secrets Manager, and CloudWatch. Allow all outbound.
resource "aws_vpc_security_group_egress_rule" "all_outbound" {
  security_group_id = aws_security_group.backup.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  tags = merge(
    {
      Name = "outgoing traffic"
    },
    local.all_tags,
  )
}
