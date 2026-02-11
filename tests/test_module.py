import json
import time
from base64 import b64decode
from datetime import datetime, timezone
from os import path as osp
from subprocess import run
from textwrap import dedent

from infrahouse_core.aws.secretsmanager import Secret
from infrahouse_core.timeout import timeout
from pytest_infrahouse import terraform_apply

from tests.conftest import (
    GH_APP_ID,
    GH_APP_INSTALLATION_ID,
    GH_APP_PEM_SECRET_NAME,
    GH_APP_PEM_SECRET_REGION,
    LOG,
    TASK_RUN_TIMEOUT,
    TERRAFORM_ROOT_DIR,
)


def test_module(
    service_network,
    keep_after,
    test_role_arn,
    aws_region,
    boto3_session,
    cleanup_ecs_task_definitions,
):
    """
    End-to-end test for the github-backup module.

    1. Deploy the module (terraform apply).
    2. Populate the module-created secret with a real GitHub App PEM key.
    3. Run the ECS Fargate task.
    4. Wait for task completion.
    5. Verify backup bundles exist in the S3 bucket.
    """
    subnet_public_ids = service_network["subnet_public_ids"]["value"]

    terraform_module_dir = osp.join(TERRAFORM_ROOT_DIR, "main")
    with open(osp.join(terraform_module_dir, "terraform.tfvars"), "w") as fp:
        fp.write(
            dedent(
                f"""
                region                         = "{aws_region}"
                subnets                        = {json.dumps(subnet_public_ids)}
                github_app_id                  = "{GH_APP_ID}"
                github_app_installation_id     = "{GH_APP_INSTALLATION_ID}"
                """
            )
        )
        if test_role_arn:
            fp.write(
                dedent(
                    f"""
                    role_arn = "{test_role_arn}"
                    """
                )
            )

    with terraform_apply(
        terraform_module_dir,
        destroy_after=not keep_after,
        json_output=True,
    ) as tf_output:
        LOG.info(json.dumps(tf_output, indent=4))

        # ── Verify all expected outputs exist ───────────────────
        assert "s3_bucket_name" in tf_output
        assert "ecs_cluster_arn" in tf_output
        assert "task_definition_arn" in tf_output
        assert "task_role_arn" in tf_output
        assert "log_group_name" in tf_output
        assert "schedule_rule_arn" in tf_output
        assert "github_app_key_secret_arn" in tf_output

        bucket_name = tf_output["s3_bucket_name"]["value"]
        assert bucket_name, "S3 bucket name should not be empty"

        cluster_arn = tf_output["ecs_cluster_arn"]["value"]
        assert cluster_arn.startswith("arn:aws:ecs:")

        cluster_name = tf_output["ecs_cluster_name"]["value"]
        task_definition_arn = tf_output["task_definition_arn"]["value"]
        security_group_id = tf_output["security_group_id"]["value"]
        module_secret_arn = tf_output["github_app_key_secret_arn"]["value"]

        cleanup_ecs_task_definitions(
            tf_output["task_definition_arn"]["value"].split("/")[-1].split(":")[0]
        )

        # ── Build and push the container image ────────────────
        account_id = tf_output["account_id"]["value"]
        ecr_repo_url = tf_output["ecr_repo_url"]["value"]

        ecr = boto3_session.client("ecr", region_name=aws_region)
        resp = ecr.get_authorization_token(registryIds=[account_id])
        data = resp["authorizationData"][0]
        userpass = b64decode(data["authorizationToken"]).decode("utf-8")
        username, password = userpass.split(":", 1)
        registry = data["proxyEndpoint"].replace("https://", "").replace("http://", "")

        run(
            ["docker", "login", "--username", username, "--password-stdin", registry],
            input=password.encode("utf-8"),
            check=True,
        )

        image_tag = f"{ecr_repo_url}:latest"
        LOG.info("Building and pushing image: %s", image_tag)
        run(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                "linux/amd64",
                "-t",
                image_tag,
                "--push",
                ".",
            ],
            cwd="container",
            check=True,
        )
        LOG.info("Image pushed successfully: %s", image_tag)

        # ── Populate the module-created secret with the PEM key ─
        # Source secret is in the control repo's region (us-west-1).
        pem_secret = Secret(
            GH_APP_PEM_SECRET_NAME,
            region=GH_APP_PEM_SECRET_REGION,
            session=boto3_session,
        )
        pem_key = pem_secret.value
        LOG.info(
            "Read PEM key from %s in %s (%d bytes)",
            GH_APP_PEM_SECRET_NAME,
            GH_APP_PEM_SECRET_REGION,
            len(pem_key),
        )

        module_secret = Secret(
            module_secret_arn,
            region=aws_region,
            session=boto3_session,
        )
        module_secret.update(pem_key)
        LOG.info("Wrote PEM key to module secret %s", module_secret_arn)

        # ── Run the ECS task ────────────────────────────────────
        ecs_client = boto3_session.client("ecs", region_name=aws_region)
        run_response = ecs_client.run_task(
            cluster=cluster_name,
            taskDefinition=task_definition_arn,
            launchType="FARGATE",
            count=1,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": subnet_public_ids,
                    "securityGroups": [security_group_id],
                    "assignPublicIp": "ENABLED",
                }
            },
        )
        assert len(run_response["tasks"]) == 1, (
            f"Expected 1 task, got {len(run_response['tasks'])}. "
            f"Failures: {run_response.get('failures', [])}"
        )

        task_arn = run_response["tasks"][0]["taskArn"]
        task_id = task_arn.split("/")[-1]
        LOG.info("Started ECS task: %s", task_id)

        # ── Wait for task to finish ─────────────────────────────
        final_status = None
        with timeout(TASK_RUN_TIMEOUT):
            while True:
                desc = ecs_client.describe_tasks(cluster=cluster_name, tasks=[task_arn])
                task = desc["tasks"][0]
                status = task["lastStatus"]
                LOG.info("Task %s status: %s", task_id, status)

                if status == "STOPPED":
                    final_status = task
                    break

                time.sleep(15)

        # ── Check task exit code ────────────────────────────────
        container = final_status["containers"][0]
        exit_code = container.get("exitCode", -1)
        stop_reason = final_status.get("stoppedReason", "")
        LOG.info(
            "Task stopped. exit_code=%d reason=%s",
            exit_code,
            stop_reason,
        )
        assert exit_code == 0, (
            f"Backup task failed with exit code {exit_code}. " f"Reason: {stop_reason}"
        )

        # ── Verify backup objects in S3 ─────────────────────────
        s3_client = boto3_session.client("s3", region_name=aws_region)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prefix = f"github-backup/{today}/"

        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
        )
        assert (
            "Contents" in response
        ), f"No objects found under s3://{bucket_name}/{prefix}"

        objects = response["Contents"]
        LOG.info(
            "Found %d objects under s3://%s/%s",
            len(objects),
            bucket_name,
            prefix,
        )
        for obj in objects:
            LOG.info("  %s  (%d bytes)", obj["Key"], obj["Size"])

        # Expect at least one .bundle file and a manifest.json
        bundle_keys = [o["Key"] for o in objects if o["Key"].endswith(".bundle")]
        manifest_keys = [
            o["Key"] for o in objects if o["Key"].endswith("manifest.json")
        ]

        assert len(bundle_keys) > 0, (
            f"No .bundle files found under {prefix}. "
            f"Keys: {[o['Key'] for o in objects]}"
        )
        assert (
            len(manifest_keys) == 1
        ), f"Expected exactly 1 manifest.json, found {len(manifest_keys)}"

        # Verify manifest content
        manifest_obj = s3_client.get_object(Bucket=bucket_name, Key=manifest_keys[0])
        manifest = json.loads(manifest_obj["Body"].read().decode("utf-8"))
        LOG.info("Manifest: %s", json.dumps(manifest, indent=2))

        assert (
            manifest["success_count"] > 0
        ), "Expected at least one successful backup in manifest"
        assert manifest["failure_count"] == 0, (
            f"Backup had {manifest['failure_count']} failures: "
            f"{manifest.get('failed', [])}"
        )
