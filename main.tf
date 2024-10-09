resource "aws_autoscaling_group" "main" {
    name_prefix           = aws_launch_template.github-backup.name
    min_size              = var.asg_min_size
    max_size              = var.asg_max_size
    vpc_zone_identifier   = var.subnets
    max_instance_lifetime = var.max_instance_lifetime_days * 24 * 3600
    instance_refresh {
        strategy = "Rolling"
        preferences {
            min_healthy_percentage = var.asg_min_healthy_percentage
        }
        triggers = ["tag"]
    }
    launch_template {
        id      = aws_launch_template.github-backup.id
        version = aws_launch_template.github-backup.latest_version
    }
    instance_maintenance_policy {
        min_healthy_percentage = var.asg_min_healthy_percentage
        max_healthy_percentage = var.asg_max_healthy_percentage
    }
    dynamic "tag" {
        for_each = merge(
            local.default_asg_tags,
            var.tags,
            data.aws_default_tags.provider.tags
        )
        content {
            key                 = tag.key
            value               = tag.value
            propagate_at_launch = true

        }
    }

    lifecycle {
        create_before_destroy = true
    }
}

resource "aws_launch_template" "github-backup" {
    name_prefix   = "infrahouse-github-backup"
    image_id      = data.aws_ami.selected.id
    instance_type = var.instance_type
    user_data     = module.userdata.userdata
    key_name      = var.key_pair_name
    vpc_security_group_ids = concat(
        [aws_security_group.backend.id],
    )
    iam_instance_profile {
        arn = module.instance_profile.instance_profile_arn
    }

    block_device_mappings {
        device_name = data.aws_ami.selected.root_device_name
        ebs {
            volume_size           = var.root_volume_size
            delete_on_termination = true
        }
    }
    tag_specifications {
        resource_type = "volume"
        tags = merge(
            data.aws_default_tags.provider.tags,
            local.default_module_tags
        )
    }
    tag_specifications {
        resource_type = "network-interface"
        tags = merge(
            data.aws_default_tags.provider.tags,
            local.default_module_tags
        )
    }

}

module "userdata" {
    source      = "registry.infrahouse.com/infrahouse/cloud-init/aws"
    version     = "1.12.4"
    environment = var.environment
    role        = "infrahouse_github_backup"
    custom_facts = {
        "infrahouse-github-backup" : {
            "app-key-url" : "secretsmanager://${data.aws_secretsmanager_secret.app_key_secret.name}"
        }
    }
}

resource "random_string" "profile_suffix" {
    length  = 12
    special = false
    upper   = false
}

module "instance_profile" {
    source       = "registry.infrahouse.com/infrahouse/instance-profile/aws"
    version      = "1.5.1"
    profile_name = "${var.service_name}-${random_string.profile_suffix.result}"
    role_name    = var.instance_role_name
    permissions  = data.aws_iam_policy_document.default_permissions.json
}
