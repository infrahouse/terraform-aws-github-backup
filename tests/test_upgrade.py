"""
Upgrade tests: apply a released version (from the registry), switch the
module source to this checkout, and verify the upgrade keeps every S3 setting
and never leaves replication on a deleted IAM role.

- From 2.0.1, a release before the s3-bucket refactor in 2.0.3 (2.0.0 and
  2.0.2 have the same addresses), the S3 settings must be moved instead of
  destroyed, and the replication role is kept. The Container Insights log
  group, which ECS creates on a running cluster, must be imported.
- From 2.0.3, which replicated with the s3-bucket module's role, this module
  takes the role over and replaces it. Replication must move to the new role
  before the old one is deleted.

Regression tests for infrahouse/terraform-aws-github-backup#31. They don't
run the ECS task or build the container image.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from os import path as osp
from subprocess import PIPE, STDOUT, CalledProcessError, run
from textwrap import dedent
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Tuple

import pytest
from boto3 import Session
from botocore.exceptions import ClientError
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
CONTAINER_INSIGHTS_LOG_GROUP = "module.main.aws_cloudwatch_log_group.container_insights"

# Retention ECS gave the Container Insights log group on a production
# cluster running 2.0.1.
ECS_LOG_GROUP_RETENTION_DAYS = 1
# How long to wait for S3 to replicate a test object, and for IAM to stop
# returning a deleted role. Replication without RTC can take minutes.
REPLICATION_TIMEOUT_SECONDS = 900
IAM_DELETE_TIMEOUT_SECONDS = 60

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
        Container Insights log group (versions before 2.0.2). The test then
        creates the group the way ECS does on a running cluster.
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
    test_role_arn: Optional[str],
    aws_region: str,
    boto3_session: Session,
    cleanup_ecs_task_definitions: Callable[[str], None],
) -> None:
    """
    Upgrade a released version to this checkout without losing any S3
    setting, and without replication pointing at a deleted role.

    1. Apply the module at ``scenario.from_version`` from the registry.
    2. Switch the source to this checkout. Before 2.0.2, create the
       Container Insights log group the way ECS does, and import it as
       docs/upgrading.md says. Plan.
    3. Assert from the plan JSON that no ``aws_s3_bucket*`` resource is
       deleted, that the expected resources are moved, that nothing else is
       deleted, and that the log group is imported.
    4. Assert from ``terraform graph -plan`` that every IAM delete waits for
       the replication update.
    5. Apply the plan. Assert from its log that replication is updated
       before any IAM object is deleted. Check both buckets, the role and
       the log group with boto3, and that a new object replicates.

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
    log_group = f"/aws/ecs/containerinsights/{scenario.service_name}/performance"
    logs = boto3_session.client("logs", region_name=aws_region)
    # Container Insights can recreate the group after a destroy, minutes
    # after the cluster is gone, so a previous run can leave it behind.
    # 2.0.2 and later create it, and a leftover would fail the first apply.
    _delete_log_group(logs, log_group)
    # Each apply registers a task definition revision in the family
    # service_name, and a destroy only deregisters it. pytest-infrahouse
    # deletes the family's revisions at the end of the session, also when
    # the test fails after the first apply.
    cleanup_ecs_task_definitions(scenario.service_name)

    try:
        with terraform_apply(
            module_dir,
            destroy_after=not keep_after,
            json_output=True,
        ) as tf_output:
            source_bucket = tf_output["s3_bucket_name"]["value"]
            replica_bucket = tf_output["replica_bucket_name"]["value"]
            assert tf_output["ecs_cluster_name"]["value"] == scenario.service_name
            LOG.info(
                "Deployed %s: source=%s replica=%s",
                scenario.from_version,
                source_bucket,
                replica_bucket,
            )

            _switch_to_local_source(module_dir, scenario.from_version)
            if scenario.import_container_insights:
                _create_log_group_like_ecs(logs, log_group)
                _write_import_block(module_dir, log_group)

            plan, graph = _plan(module_dir)
            changes = plan["resource_changes"]
            _assert_no_s3_deletes(changes)
            _assert_moved(changes, scenario)
            _assert_only_expected_deletes(changes, scenario.expected_deletes)
            if scenario.import_container_insights:
                _assert_log_group_imported(changes)
            _assert_iam_deletes_wait_for_replication(graph, scenario.expected_deletes)
            old_replication_role = _change_by_address(changes, REPLICATION_CONFIG)[
                "change"
            ]["before"]["role"]

            apply_log = _apply_plan(module_dir)
            _assert_replication_updated_before_iam_deletes(
                apply_log, scenario.expected_deletes
            )

            _assert_bucket_settings(
                boto3_session, aws_region, source_bucket, replica_bucket
            )
            _assert_replication_role(
                boto3_session,
                aws_region,
                source_bucket,
                old_replication_role,
                scenario,
            )
            _assert_log_group_retention(
                logs,
                log_group,
                _change_by_address(changes, CONTAINER_INSIGHTS_LOG_GROUP)["change"][
                    "after"
                ]["retention_in_days"],
            )
            _assert_object_replicates(
                boto3_session,
                aws_region,
                source_bucket,
                replica_bucket,
                f"github-backup/upgrade-test/from-{scenario.from_version}.txt",
            )
    finally:
        # If the test failed before the import, no state owns the group,
        # and the destroy doesn't delete it.
        if not keep_after:
            _delete_log_group(logs, log_group)


def _plan(module_dir: str) -> Tuple[Dict, str]:
    """
    Plan the test root module and read the plan back.

    Saves the plan to ``PLAN_FILE`` and its graph to ``GRAPH_FILE``.

    :param module_dir: Path to the test root module.
    :return: The plan JSON from ``terraform show -json``, and the DOT output
        of ``terraform graph -plan``.
    :raise CalledProcessError: If terraform exits with non-zero.
    """
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
    return plan, graph


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
    old_role_name = old_replication_role.split("/")[-1]
    # IAM is eventually consistent: a role deleted seconds ago can still be
    # returned for a short while.
    deadline = time.monotonic() + IAM_DELETE_TIMEOUT_SECONDS
    while True:
        try:
            iam.get_role(RoleName=old_role_name)
        except iam.exceptions.NoSuchEntityException:
            return
        assert (
            time.monotonic() < deadline
        ), f"The {scenario.from_version} role {old_role_name} still exists"
        time.sleep(5)


def _assert_iam_deletes_wait_for_replication(
    graph: str, expected_deletes: FrozenSet[str]
) -> None:
    """
    Fail unless the plan graph deletes exactly the expected IAM objects, and
    each delete waits, directly or through other nodes, for the replication
    update.

    In ``terraform graph`` output, ``"A" -> "B"`` means A waits for B.

    :param graph: DOT output of ``terraform graph -plan``.
    :param expected_deletes: Addresses the plan deletes.
    """
    edges: Dict[str, Set[str]] = {}
    nodes: Set[str] = set()
    for source, target in re.findall(r'"([^"]+)" -> "([^"]+)"', graph):
        edges.setdefault(source, set()).add(target)
        nodes.update((source, target))

    replication_node = f"[root] {REPLICATION_CONFIG}"
    assert replication_node in nodes, f"{replication_node} not in the plan graph"
    iam_deletes = {
        node: address
        for node in nodes
        for address in (REPLICATION_ROLE, REPLICATION_POLICY)
        if node.startswith(f"[root] {address} (destroy")
    }
    LOG.info("IAM deletes in the plan graph: %s", sorted(iam_deletes))
    expected_iam_deletes = expected_deletes & {REPLICATION_ROLE, REPLICATION_POLICY}
    assert set(iam_deletes.values()) == expected_iam_deletes, (
        f"The plan graph deletes {sorted(set(iam_deletes.values()))}, "
        f"expected {sorted(expected_iam_deletes)}"
    )
    for node in iam_deletes:
        assert _reaches(edges, node, replication_node), (
            f"{node} doesn't wait for {replication_node}: "
            "replication would point at a deleted IAM object"
        )


def _assert_replication_updated_before_iam_deletes(
    apply_log: str, expected_deletes: FrozenSet[str]
) -> None:
    """
    Fail unless the apply log deletes exactly the expected IAM objects, and
    only after the replication update completes.

    :param apply_log: Output of ``terraform apply -no-color``.
    :param expected_deletes: Addresses the plan deletes.
    """
    lines = apply_log.splitlines()
    updated = [
        number
        for number, line in enumerate(lines)
        if line.startswith(f"{REPLICATION_CONFIG}: Modifications complete")
    ]
    deleted: Dict[int, str] = {
        number: address
        for number, line in enumerate(lines)
        for address in (REPLICATION_ROLE, REPLICATION_POLICY)
        if re.match(
            rf"{re.escape(address)}( \(deposed object \w+\))?: Destroying\.\.\.", line
        )
    }
    expected_iam_deletes = expected_deletes & {REPLICATION_ROLE, REPLICATION_POLICY}
    assert set(deleted.values()) == expected_iam_deletes, (
        f"The apply deletes {sorted(set(deleted.values()))}, "
        f"expected {sorted(expected_iam_deletes)}"
    )
    iam_deletes = list(deleted)
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


def _create_log_group_like_ecs(logs, log_group: str) -> None:
    """
    Create the Container Insights log group as ECS does on a running cluster.

    2.0.2 started managing this group. On a cluster deployed before, ECS has
    already created it, with a retention ECS picks: 1 day on a production
    cluster running 2.0.1. With no task run, the test creates it instead.

    :param logs: CloudWatch Logs client in the cluster's region.
    :param log_group: Log group name.
    """
    try:
        logs.create_log_group(logGroupName=log_group)
    except logs.exceptions.ResourceAlreadyExistsException:
        LOG.info("%s already exists", log_group)
    logs.put_retention_policy(
        logGroupName=log_group, retentionInDays=ECS_LOG_GROUP_RETENTION_DAYS
    )
    LOG.info(
        "Created %s with %d-day retention, like ECS",
        log_group,
        ECS_LOG_GROUP_RETENTION_DAYS,
    )


def _delete_log_group(logs, log_group: str) -> None:
    """
    Delete a log group if it still exists.

    :param logs: CloudWatch Logs client in the log group's region.
    :param log_group: Log group name.
    """
    try:
        logs.delete_log_group(logGroupName=log_group)
        LOG.info("Deleted %s, which no Terraform state owns", log_group)
    except logs.exceptions.ResourceNotFoundException:
        pass


def _write_import_block(module_dir: str, log_group: str) -> None:
    """
    Write the ``import`` block docs/upgrading.md tells callers to add.

    :param module_dir: Path to the test root module.
    :param log_group: Name of the existing Container Insights log group.
    """
    with open(osp.join(module_dir, IMPORTS_FILE), "w", encoding="utf-8") as fp:
        fp.write(dedent(f"""\
                import {{
                  to = {CONTAINER_INSIGHTS_LOG_GROUP}
                  id = "{log_group}"
                }}
                """))


def _assert_log_group_imported(changes: List[Dict]) -> None:
    """
    Fail unless the plan imports the Container Insights log group and sets
    the module's retention on it, instead of creating it.

    :param changes: ``resource_changes`` from ``terraform show -json``.
    """
    change = _change_by_address(changes, CONTAINER_INSIGHTS_LOG_GROUP)["change"]
    assert change.get(
        "importing"
    ), f"{CONTAINER_INSIGHTS_LOG_GROUP} is not imported: {change['actions']}"
    assert change["actions"] == [
        "update"
    ], f"{CONTAINER_INSIGHTS_LOG_GROUP}: plan says {change['actions']}, expected an update"
    assert change["before"]["retention_in_days"] == ECS_LOG_GROUP_RETENTION_DAYS
    assert change["after"]["retention_in_days"] != ECS_LOG_GROUP_RETENTION_DAYS


def _assert_log_group_retention(logs, log_group: str, retention_days: int) -> None:
    """
    Fail unless the log group has the given retention.

    :param logs: CloudWatch Logs client in the log group's region.
    :param log_group: Log group name.
    :param retention_days: Expected retention, in days.
    """
    groups = logs.describe_log_groups(logGroupNamePrefix=log_group)["logGroups"]
    actual = {group["logGroupName"]: group.get("retentionInDays") for group in groups}
    assert (
        actual.get(log_group) == retention_days
    ), f"{log_group} retention is {actual.get(log_group)}, expected {retention_days}"


def _assert_object_replicates(
    boto3_session: Session,
    aws_region: str,
    source_bucket: str,
    replica_bucket: str,
    key: str,
) -> None:
    """
    Write an object to the source bucket and wait until S3 replicates it.

    Proves the role replication uses after the upgrade can replicate, not
    only that it exists.

    :param boto3_session: Session with the test role.
    :param aws_region: Region of the source bucket.
    :param source_bucket: Name of the source bucket.
    :param replica_bucket: Name of the replica bucket.
    :param key: Object key to write.
    """
    s3_source = boto3_session.client("s3", region_name=aws_region)
    s3_replica = boto3_session.client("s3", region_name=REPLICA_REGION)
    version_id = s3_source.put_object(
        Bucket=source_bucket, Key=key, Body=b"replication check\n"
    )["VersionId"]

    deadline = time.monotonic() + REPLICATION_TIMEOUT_SECONDS
    while True:
        status = s3_source.head_object(
            Bucket=source_bucket, Key=key, VersionId=version_id
        ).get("ReplicationStatus")
        assert status != "FAILED", f"S3 failed to replicate s3://{source_bucket}/{key}"
        if status == "COMPLETED":
            break
        assert (
            time.monotonic() < deadline
        ), f"s3://{source_bucket}/{key} not replicated after {REPLICATION_TIMEOUT_SECONDS}s: {status}"
        time.sleep(10)

    try:
        s3_replica.head_object(Bucket=replica_bucket, Key=key, VersionId=version_id)
    except ClientError as err:
        raise AssertionError(
            f"S3 reports s3://{source_bucket}/{key} replicated, "
            f"but the replica doesn't have version {version_id}"
        ) from err
    LOG.info("s3://%s/%s replicated to %s", source_bucket, key, replica_bucket)


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
    test_role_arn: Optional[str],
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
