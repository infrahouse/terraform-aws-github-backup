resource "aws_security_group" "backend" {
  description = "Backend security group for service ${var.service_name}"
  name_prefix = "${var.service_name}-"
  vpc_id      = data.aws_subnet.selected.vpc_id

  tags = merge(
    {
      Name : "${var.service_name} backend"
    },
    local.default_module_tags
  )
}

resource "aws_vpc_security_group_ingress_rule" "backend_ssh_local" {
  description       = "SSH access from the service ${var.service_name} VPC"
  security_group_id = aws_security_group.backend.id
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
  cidr_ipv4         = data.aws_vpc.service.cidr_block
  tags = merge(
    {
      Name = "SSH local"
    },
    local.default_module_tags
  )
}

resource "aws_vpc_security_group_ingress_rule" "backend_icmp" {
  description       = "Allow all ICMP traffic"
  security_group_id = aws_security_group.backend.id
  from_port         = -1
  to_port           = -1
  ip_protocol       = "icmp"
  cidr_ipv4         = "0.0.0.0/0"
  tags = merge(
    {
      Name = "ICMP traffic"
    },
    local.default_module_tags
  )
}

resource "aws_vpc_security_group_egress_rule" "backend_outgoing" {
  security_group_id = aws_security_group.backend.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  tags = merge(
    {
      Name = "outgoing traffic"
    },
    local.default_module_tags
  )
}
