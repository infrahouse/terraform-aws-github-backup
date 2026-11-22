"""
Upgrade tests: apply a released version (from the registry), switch the
module source to this checkout, and verify the upgrade keeps every S3 setting
and never leaves replication on a deleted IAM role.

- From 2.0.1, the last release before the s3-bucket refactor, the S3 settings
  must be moved instead of destroyed, and the replication role is kept.
- From 2.0.3, which replicated with the s3-bucket module's role, this module
  takes the role over and replaces it. Replication must move to the new role
  before the old one is deleted.

Regression tests for infrahouse/terraform-aws-github-backup#31. They don't
run the ECS task or build the container image.
"""

import json
import os
import re
from dataclasses import dataclass, field
from os import path as osp
from subprocess import PIPE, STDOUT, CalledProcessError, run
from textwrap import dedent
from typing import Dict, FrozenSet, List, Set

import pytest
from boto3 import Session
from pytest_infrahouse import terraform_apply

from tests.conftest import (
    GH_APP_ID,
    GH_APP_INSTALLATION_ID,
    LOG,
    TERRAFORM_ROOT_DIR,
)

REGISTRY_SOURCE = "registry.infrahouse.com/infrahouse/github-backup/aws"
REPLICA_REGION = "us-east-1"
PLAN_FILE = "tfplan"
GRAPH_FILE = "tfplan.dot"
IMPORTS_FILE = "imports.tf"

REPLICATION_CONFIG = (
    "module.main.module.backup_bucket.aws_s3_bucket_replication_configuration.this[0]"
)
REPLICATION_ROLE = "module.main.aws_iam_role.replication"
REPLICATION_POLICY = "module.main.aws_iam_role_policy.replication"

EXPECTED_LIFECYCLE_RULE_IDS = {
    "expire-old-backups",
    "abort-incomplete-multipart-uploads",
}


@dataclass(frozen=True)
class UpgradeScenario:
    """
    A released version to upgrade from, and what its upgrade plan must show.

    :param from_version: Registry version to apply first.
    :param expected_moves: Old address to new address for each resource the
        plan must show as moved.
    :param move_actions: Plan actions allowed for a moved resource.
    :param expected_deletes: Addresses the plan may delete; nothing else.
    :param replaces_replication_role: True if the upgrade replaces the role
        that replication uses, False if it keeps it.
    :param import_container_insights: True if the caller must import the
        Container Insights log group (versions before 2.0.2).
    """

    from_version: str
    expected_moves: Dict[str, str]
    move_actions: List[List[str]]
    expected_deletes: FrozenSet[str] = field(default_factory=frozenset)
    replaces_replication_role: bool = False
    import_container_insights: bool = False

    @property
    def service_name(self) -> str:
        """
        Service name for this scenario's deployment.

        Distinct per scenario and from test_module's default, so no two
        deployments share bucket, cluster or role names, and a bucket name
        isn't reused right after a destroy.

        :return: The service name.
        """
        return f"github-backup-upgrade-{self.from_version.replace('.', '')}"


# 2.0.1 address -> 2.0.3+ address. Each pair manages the same bucket
# setting, so the plan must show it as moved and updated in place, never
# destroyed. The replication role and policy keep their 2.0.1 addresses.
FROM_2_0_1 = UpgradeScenario(
    from_version="2.0.1",
    expected_moves={
        "module.main.aws_s3_bucket.replica": "module.main.module.backup_bucket.aws_s3_bucket.replica[0]",
        "module.main.aws_s3_bucket_versioning.replica": (
            "module.main.module.backup_bucket.aws_s3_bucket_versioning.replica[0]"
        ),
        "module.main.aws_s3_bucket_public_access_block.replica": (
            "module.main.module.backup_bucket.aws_s3_bucket_public_access_block.replica[0]"
        ),
        "module.main.aws_s3_bucket_server_side_encryption_configuration.replica": (
            "module.main.module.backup_bucket.aws_s3_bucket_server_side_encryption_configuration.replica[0]"
        ),
        "module.main.aws_s3_bucket_replication_configuration.backup": REPLICATION_CONFIG,
        "module.main.aws_s3_bucket_lifecycle_configuration.backup": (
            'module.main.aws_s3_bucket_lifecycle_configuration.backup["source"]'
        ),
        "module.main.aws_s3_bucket_lifecycle_configuration.replica": (
            'module.main.aws_s3_bucket_lifecycle_configuration.backup["replica"]'
        ),
    },
    move_actions=[["no-op"], ["update"]],
    import_container_insights=True,
)

# 2.0.3 replicated with the s3-bucket module's role. This module takes the
# role and its policy over under its own name prefix, which replaces them:
# create the new ones first, delete the old ones last.
FROM_2_0_3 = UpgradeScenario(
    from_version="2.0.3",
    expected_moves={
        "module.main.module.backup_bucket.aws_iam_role.replication[0]": REPLICATION_ROLE,
        "module.main.module.backup_bucket.aws_iam_role_policy.replication[0]": REPLICATION_POLICY,
    },
    move_actions=[["create", "delete"]],
    expected_deletes=frozenset({REPLICATION_ROLE, REPLICATION_POLICY}),
    replaces_replication_role=True,
)


@pytest.mark.parametrize(
    "scenario", [FROM_2_0_1, FROM_2_0_3], ids=lambda s: f"from-{s.from_version}"
)
def test_upgrade(
    scenario: UpgradeScenario,
    service_network: Dict,
    keep_after: bool,
    test_role_arn: str,
    aws_region: str,
    boto3_session: Session,
) -> None:
    """
    Upgrade a released version to this checkout without losing any S3
    setting, and without replication pointing at a deleted role.

    1. Apply the module at ``scenario.from_version`` from the registry.
    2. Switch the source to this checkout and plan.
    3. Assert from the plan JSON that no ``aws_s3_bucket*`` resource is
       deleted, that the expected resources are moved, and that nothing else
       is deleted.
    4. Assert from ``terraform graph -plan`` that every IAM delete waits for
       the replication update.
    5. Apply the plan. Assert from its log that replication is updated
       before any IAM object is deleted, and check both buckets with boto3.

    Start from a clean account: with ``--keep-after``, the next run would
    re-apply the old version on top of upgraded state.
    """
    module_dir = osp.join(TERRAFORM_ROOT_DIR, "upgrade")
    _write_tfvars(
        module_dir,
        aws_region,
        service_network["subnet_private_ids"]["value"],
        test_role_arn,
        scenario.service_name,
    )
    _remove_generated_files(module_dir)
    _write_main_tf(module_dir, _registry_source(scenario.from_version))

    with terraform_apply(
        module_dir,
        destroy_after=not keep_after,
        json_output=True,
    ) as tf_output:
        source_bucket = tf_output["s3_bucket_name"]["value"]
        replica_bucket = tf_output["replica_bucket_name"]["value"]
        cluster_name = tf_output["ecs_cluster_name"]["value"]
        LOG.info(
            "Deployed %s: source=%s replica=%s",
            scenario.from_version,
            source_bucket,
            replica_bucket,
        )

        _switch_to_local_source(module_dir, scenario.from_version)
        if scenario.import_container_insights:
            _import_container_insights_log_group(
                module_dir, boto3_session, aws_region, cluster_name
            )

        run(
            [
                "terraform",
                "plan",
                "-var-file=terraform.tfvars",
                "-input=false",
                "-no-color",
                f"-out={PLAN_FILE}",
            ],
            cwd=module_dir,
            check=True,
        )
        plan = json.loads(_terraform_stdout(module_dir, "show", "-json", PLAN_FILE))
        graph = _terraform_stdout(module_dir, "graph", f"-plan={PLAN_FILE}")
        with open(osp.join(module_dir, GRAPH_FILE), "w", encoding="utf-8") as fp:
            fp.write(graph)

        changes = plan["resource_changes"]
        _assert_no_s3_deletes(changes)
        _assert_moved(changes, scenario)
        _assert_only_expected_deletes(changes, scenario.expected_deletes)
        _assert_iam_deletes_wait_for_replication(graph)
        old_replication_role = _change_by_address(changes, REPLICATION_CONFIG)[
            "change"
        ]["before"]["role"]

        apply_log = _apply_plan(module_dir)
        _assert_replication_updated_before_iam_deletes(apply_log)

        _assert_bucket_settings(
            boto3_session, aws_region, source_bucket, replica_bucket
        )
        _assert_replication_role(
            boto3_session, aws_region, source_bucket, old_replication_role, scenario
        )


def _apply_plan(module_dir: str) -> str:
    """
    Apply the saved plan and return its log.

    :param module_dir: Path to the test root module.
    :return: Combined standard output and error of ``terraform apply``.
    :raise CalledProcessError: If the apply fails.
    """
    result = run(
        ["terraform", "apply", "-input=false", "-no-color", "-auto-approve", PLAN_FILE],
        cwd=module_dir,
        stdout=PIPE,
        stderr=STDOUT,
        text=True,
    )
    LOG.info("terraform apply:\n%s", result.stdout)
    result.check_returncode()
    return result.stdout


def _assert_bucket_settings(
    boto3_session: Session,
    aws_region: str,
    source_bucket: str,
    replica_bucket: str,
) -> None:
    """
    Check every S3 setting from issue #31 on the live buckets.

    :param boto3_session: Session with the test role.
    :param aws_region: Region of the source bucket.
    :param source_bucket: Name of the source bucket.
    :param replica_bucket: Name of the replica bucket.
    """
    s3_source = boto3_session.client("s3", region_name=aws_region)
    s3_replica = boto3_session.client("s3", region_name=REPLICA_REGION)

    versioning = s3_replica.get_bucket_versioning(Bucket=replica_bucket)
    assert (
        versioning.get("Status") == "Enabled"
    ), f"Replica versioning is {versioning.get('Status')!r}, expected 'Enabled'"

    replication = s3_source.get_bucket_replication(Bucket=source_bucket)[
        "ReplicationConfiguration"
    ]
    LOG.info("Replication configuration: %s", json.dumps(replication, indent=2))
    enabled_destinations = [
        rule["Destination"]["Bucket"]
        for rule in replication["Rules"]
        if rule["Status"] == "Enabled"
    ]
    assert enabled_destinations == [
        f"arn:aws:s3:::{replica_bucket}"
    ], f"Unexpected replication destinations: {enabled_destinations}"

    public_access_block = s3_replica.get_public_access_block(Bucket=replica_bucket)[
        "PublicAccessBlockConfiguration"
    ]
    assert all(
        public_access_block.values()
    ), f"Replica public access block is not fully enabled: {public_access_block}"

    for client, bucket in ((s3_source, source_bucket), (s3_replica, replica_bucket)):
        rules = client.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
        rule_ids = {rule["ID"] for rule in rules}
        assert (
            rule_ids == EXPECTED_LIFECYCLE_RULE_IDS
        ), f"Lifecycle rules on {bucket}: {rule_ids}, expected {EXPECTED_LIFECYCLE_RULE_IDS}"


def _assert_replication_role(
    boto3_session: Session,
    aws_region: str,
    source_bucket: str,
    old_replication_role: str,
    scenario: UpgradeScenario,
) -> None:
    """
    Check the role replication uses after the upgrade.

    It must exist and have an inline policy. From 2.0.1 it is the old role;
    from 2.0.3 it is a new one, and the old role is gone.

    :param boto3_session: Session with the test role.
    :param aws_region: Region of the source bucket.
    :param source_bucket: Name of the source bucket.
    :param old_replication_role: ARN of the role replication used before
        the upgrade.
    :param scenario: The upgrade scenario.
    """
    s3_source = boto3_session.client("s3", region_name=aws_region)
    role_arn = s3_source.get_bucket_replication(Bucket=source_bucket)[
        "ReplicationConfiguration"
    ]["Role"]
    iam = boto3_session.client("iam")
    role_name = role_arn.split("/")[-1]
    policies = iam.list_role_policies(RoleName=role_name)["PolicyNames"]
    assert policies, f"Replication role {role_name} has no inline policy"

    if not scenario.replaces_replication_role:
        assert role_arn == old_replication_role, (
            f"Replication moved from {old_replication_role} to {role_arn}; "
            f"the upgrade from {scenario.from_version} must keep the role"
        )
        return

    assert (
        role_arn != old_replication_role
    ), f"Replication still uses the {scenario.from_version} role {old_replication_role}"
    with pytest.raises(iam.exceptions.NoSuchEntityException):
        iam.get_role(RoleName=old_replication_role.split("/")[-1])


def _assert_iam_deletes_wait_for_replication(graph: str) -> None:
    """
    Fail unless every IAM role or policy delete in the plan graph waits,
    directly or through other nodes, for the replication update.

    In ``terraform graph`` output, ``"A" -> "B"`` means A waits for B.

    :param graph: DOT output of ``terraform graph -plan``.
    """
    edges: Dict[str, Set[str]] = {}
    for source, target in re.findall(r'"([^"]+)" -> "([^"]+)"', graph):
        edges.setdefault(source, set()).add(target)

    replication_node = f"[root] {REPLICATION_CONFIG}"
    iam_deletes = [
        node
        for node in edges
        if node.startswith(
            (
                f"[root] {REPLICATION_ROLE} (destroy",
                f"[root] {REPLICATION_POLICY} (destroy",
            )
        )
    ]
    LOG.info("IAM deletes in the plan graph: %s", iam_deletes)
    for node in iam_deletes:
        assert _reaches(edges, node, replication_node), (
            f"{node} doesn't wait for {replication_node}: "
            "replication would point at a deleted IAM object"
        )


def _assert_replication_updated_before_iam_deletes(apply_log: str) -> None:
    """
    Fail if the apply log deletes an IAM role or policy before the
    replication update completes.

    :param apply_log: Output of ``terraform apply -no-color``.
    """
    lines = apply_log.splitlines()
    updated = [
        number
        for number, line in enumerate(lines)
        if line.startswith(f"{REPLICATION_CONFIG}: Modifications complete")
    ]
    iam_deletes = [
        number
        for number, line in enumerate(lines)
        if line.startswith((REPLICATION_ROLE, REPLICATION_POLICY))
        and "Destroying..." in line
    ]
    if not iam_deletes:
        return
    assert updated, "The apply deletes IAM objects but never updates replication"
    assert updated[0] < min(iam_deletes), (
        "The apply deletes an IAM object before replication moves off it:\n"
        + "\n".join(lines[number] for number in sorted(iam_deletes + updated))
    )


def _assert_moved(changes: List[Dict], scenario: UpgradeScenario) -> None:
    """
    Fail unless every expected resource is moved, with an allowed action.

    :param changes: ``resource_changes`` from ``terraform show -json``.
    :param scenario: The upgrade scenario.
    """
    for old_address, new_address in scenario.expected_moves.items():
        change = _change_by_address(changes, new_address)
        assert (
            change.get("previous_address") == old_address
        ), f"{new_address} is not moved from {old_address}: {change.get('previous_address')}"
        assert change["change"]["actions"] in scenario.move_actions, (
            f"{new_address}: plan says {change['change']['actions']}, "
            f"expected one of {scenario.move_actions}"
        )


def _assert_no_s3_deletes(changes: List[Dict]) -> None:
    """
    Fail if the plan deletes any ``aws_s3_bucket*`` resource.

    :param changes: ``resource_changes`` from ``terraform show -json``.
    """
    s3_deletes = [
        change["address"]
        for change in changes
        if change["type"].startswith("aws_s3_bucket")
        and "delete" in change["change"]["actions"]
    ]
    assert not s3_deletes, (
        "The upgrade deletes S3 resources. A bucket has only one of each "
        f"setting, so these must be moved instead: {s3_deletes}"
    )


def _assert_only_expected_deletes(
    changes: List[Dict], expected_deletes: FrozenSet[str]
) -> None:
    """
    Fail if the plan deletes anything but the expected resources.

    :param changes: ``resource_changes`` from ``terraform show -json``.
    :param expected_deletes: Addresses the plan may delete.
    """
    deletes = {
        change["address"]
        for change in changes
        if "delete" in change["change"]["actions"]
    }
    assert deletes == set(
        expected_deletes
    ), f"Upgrade deletes {sorted(deletes)}, expected {sorted(expected_deletes)}"


def _change_by_address(changes: List[Dict], address: str) -> Dict:
    """
    Find a resource change by its address.

    :param changes: ``resource_changes`` from ``terraform show -json``.
    :param address: Resource instance address.
    :return: The matching resource change.
    :raise AssertionError: If the plan has no change for the address.
    """
    for change in changes:
        if change["address"] == address:
            return change
    raise AssertionError(f"{address} not found in the plan")


def _import_container_insights_log_group(
    module_dir: str, boto3_session: Session, aws_region: str, cluster_name: str
) -> None:
    """
    Import the Container Insights log group if ECS already created it.

    2.0.2 manages this log group, which ECS creates on its own for a
    running cluster. Callers add the same ``import`` block to their root
    module (see docs/upgrading.md). With no task run, ECS may not have
    created it yet, in which case the module creates it.

    :param module_dir: Path to the test root module.
    :param boto3_session: Session with the test role.
    :param aws_region: Region of the ECS cluster.
    :param cluster_name: ECS cluster name.
    """
    log_group = f"/aws/ecs/containerinsights/{cluster_name}/performance"
    logs = boto3_session.client("logs", region_name=aws_region)
    existing = logs.describe_log_groups(logGroupNamePrefix=log_group)["logGroups"]
    if not any(group["logGroupName"] == log_group for group in existing):
        LOG.info("%s doesn't exist yet; the module will create it", log_group)
        return

    LOG.info("%s exists; importing it", log_group)
    with open(osp.join(module_dir, IMPORTS_FILE), "w", encoding="utf-8") as fp:
        fp.write(dedent(f"""\
                import {{
                  to = module.main.aws_cloudwatch_log_group.container_insights
                  id = "{log_group}"
                }}
                """))


def _reaches(edges: Dict[str, Set[str]], start: str, goal: str) -> bool:
    """
    Tell whether ``goal`` is reachable from ``start`` along graph edges.

    :param edges: Adjacency sets, from node to the nodes it waits for.
    :param start: Node to start from.
    :param goal: Node to look for.
    :return: True if a path from ``start`` to ``goal`` exists.
    """
    seen = set()
    pending = [start]
    while pending:
        node = pending.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        pending.extend(edges.get(node, ()))
    return False


def _registry_source(version: str) -> str:
    """
    Build the ``source`` and ``version`` lines for a registry release.

    :param version: Module version.
    :return: Lines for the module block.
    """
    return f'source  = "{REGISTRY_SOURCE}"\n  version = "{version}"'


def _remove_generated_files(module_dir: str) -> None:
    """
    Remove files a previous run generated, so the first apply starts clean.

    :param module_dir: Path to the test root module.
    """
    for name in (IMPORTS_FILE, PLAN_FILE, GRAPH_FILE):
        file_path = osp.join(module_dir, name)
        if osp.exists(file_path):
            os.remove(file_path)


def _switch_to_local_source(module_dir: str, from_version: str) -> None:
    """
    Point the test root module at this checkout and re-initialize it.

    If ``terraform init`` fails, restore the registry source so the
    ``terraform destroy`` in ``terraform_apply`` can still run.

    :param module_dir: Path to the test root module.
    :param from_version: Registry version to restore on failure.
    """
    _write_main_tf(module_dir, 'source = "../../"')
    try:
        run(["terraform", "init", "-no-color"], cwd=module_dir, check=True)
    except CalledProcessError:
        _write_main_tf(module_dir, _registry_source(from_version))
        raise


def _terraform_stdout(module_dir: str, *args: str) -> str:
    """
    Run a terraform subcommand and return its standard output.

    :param module_dir: Path to the test root module.
    :param args: Terraform subcommand and its arguments.
    :return: Standard output of the command.
    :raise CalledProcessError: If terraform exits with non-zero.
    """
    return run(
        ["terraform", *args],
        cwd=module_dir,
        check=True,
        stdout=PIPE,
        text=True,
    ).stdout


def _write_main_tf(module_dir: str, source: str) -> None:
    """
    Write the module block with the given source.

    :param module_dir: Path to the test root module.
    :param source: The ``source`` (and ``version``) lines of the module block.
    """
    with open(osp.join(module_dir, "main.tf"), "w", encoding="utf-8") as fp:
        fp.write(dedent("""\
                module "main" {
                  %s

                  github_app_id              = var.github_app_id
                  github_app_installation_id = var.github_app_installation_id
                  alarm_emails               = ["devops-test@infrahouse.com"]
                  # ecs-tester, not the Terraform caller role: the caller already
                  # gets admin access through the secret module.
                  github_app_key_secret_writers = [data.aws_iam_role.ecs_tester.arn]
                  replica_region                = "%s"
                  subnets                       = var.subnets
                  service_name                  = var.service_name
                  environment                   = "development"
                  force_destroy                 = true
                }
                """) % (source, REPLICA_REGION))


def _write_tfvars(
    module_dir: str,
    aws_region: str,
    subnets: List[str],
    test_role_arn: str,
    service_name: str,
) -> None:
    """
    Write ``terraform.tfvars`` for the test root module.

    :param module_dir: Path to the test root module.
    :param aws_region: Region to deploy into.
    :param subnets: Private subnet IDs for the Fargate task.
    :param test_role_arn: Role for the AWS provider to assume, if any.
    :param service_name: Service name for the deployment.
    """
    with open(osp.join(module_dir, "terraform.tfvars"), "w", encoding="utf-8") as fp:
        fp.write(dedent(f"""\
                region                     = "{aws_region}"
                subnets                    = {json.dumps(subnets)}
                github_app_id              = "{GH_APP_ID}"
                github_app_installation_id = "{GH_APP_INSTALLATION_ID}"
                service_name               = "{service_name}"
                """))
        if test_role_arn:
            fp.write(f'role_arn                   = "{test_role_arn}"\n')
