import json
from os import path as osp
from textwrap import dedent

from pytest_infrahouse import terraform_apply

from tests.conftest import (
    LOG,
    TERRAFORM_ROOT_DIR,
)


def test_module(service_network, keep_after, test_role_arn, aws_region):
    subnet_public_ids = service_network["subnet_public_ids"]["value"]

    # Create ECS with httpd container
    terraform_module_dir = osp.join(TERRAFORM_ROOT_DIR, "main")
    with open(osp.join(terraform_module_dir, "terraform.tfvars"), "w") as fp:
        fp.write(
            dedent(
                f"""
                region   = "{aws_region}"
                subnets  = {json.dumps(subnet_public_ids)}
                """
            )
        )
        if test_role_arn:
            fp.write(
                dedent(
                    f"""
                    role_arn      = "{test_role_arn}"
                    """
                )
            )

    with terraform_apply(
        terraform_module_dir,
        destroy_after=not keep_after,
        json_output=True,
    ) as tf_httpd_output:
        LOG.info(json.dumps(tf_httpd_output, indent=4))
