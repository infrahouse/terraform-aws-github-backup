# Troubleshooting

This page covers common issues, failure scenarios, and restore procedures.

## Alarms and Their Meaning

### `backup_failure` fires

**Symptom:** SNS email says "One or more GitHub repositories failed to back up."

**What it means:** The task ran but the backup script published a `BackupFailure` metric — at
least one repo failed to clone, bundle, or upload.

**Diagnosis:**

```bash
LOG_GROUP="$(terraform output -raw log_group_name)"
aws logs tail "$LOG_GROUP" --since 1d --filter-pattern 'ERROR'
```

**Common causes:**

- GitHub App permissions were reduced after install (the task can see the repo but can't read
  `Contents`)
- A repo exceeded `task_ephemeral_storage_gb` — mirror + bundle didn't fit on disk
- Transient GitHub API rate limit or outage
- S3 bucket permissions changed out-of-band

**Fixes:**

- For disk space: raise `task_ephemeral_storage_gb`.
- For permissions: verify the GitHub App has `Contents: Read-only` and `Metadata: Read-only`.
- For transient failures: the next scheduled run usually recovers without intervention.

### `task_not_running` fires

**Symptom:** SNS email says "GitHub backup task has not run in the last 24 hours."

**What it means:** No `BackupSuccess` metric was published during the evaluation period. Either
EventBridge didn't fire, ECS failed to start the task, or the container crashed before emitting
metrics.

This alarm uses `treat_missing_data = breaching`, so a task that can't even start will trigger it.

**Diagnosis:**

```bash
# Did EventBridge actually invoke RunTask?
aws cloudwatch get-metric-statistics \
  --namespace AWS/Events \
  --metric-name Invocations \
  --dimensions Name=RuleName,Value="$(terraform output -raw service_name)-schedule" \
  --start-time "$(date -u -v-2d +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 86400 --statistics Sum

# Did any tasks actually start?
CLUSTER="$(terraform output -raw ecs_cluster_name)"
aws ecs list-tasks --cluster "$CLUSTER" --desired-status STOPPED --max-results 10
```

**Common causes:**

- The GitHub App PEM was never written to Secrets Manager (first-deploy mistake)
- The private key in Secrets Manager is malformed / not a valid PEM
- Subnets lost internet access (NAT gateway removed, route table changed)
- The image tag moved and introduced a regression (pin to a SHA in `image_uri`)

## Restore Procedures

Git bundles are portable and self-contained. Each bundle is a full mirror at the time of backup —
all branches, tags, and history.

### Restore a single repository

```bash
# Download the bundle from S3
aws s3 cp s3://BUCKET/github-backup/2026-04-16/your-org/repo.bundle repo.bundle

# Verify the bundle
git bundle verify repo.bundle

# Clone from the bundle
git clone repo.bundle repo-restored

# Push back to GitHub (if recreating the repo)
cd repo-restored
git remote set-url origin git@github.com:your-org/repo.git
git push --mirror origin
```

### Restore from the replica region

If the primary region is unavailable:

```bash
aws s3 cp s3://BUCKET-replica/github-backup/2026-04-16/your-org/repo.bundle repo.bundle \
  --region REPLICA_REGION

# Continue with the standard restore steps above
```

### Restore every repo from a specific date

```bash
# List available backup dates
aws s3 ls s3://BUCKET/github-backup/

# Download every bundle from one date
aws s3 cp s3://BUCKET/github-backup/2026-04-16/ ./restore/ --recursive

# Inspect the manifest
cat restore/manifest.json

# Clone each bundle
for bundle in restore/your-org/*.bundle; do
  repo_name="$(basename "$bundle" .bundle)"
  git clone "$bundle" "restored/$repo_name"
done
```

### Attach a bundle as a remote on an existing clone

Useful when you just want to pull objects from the backup without re-cloning:

```bash
git remote add backup repo.bundle
git fetch backup
```

## Failure Scenarios Reference

| Scenario | Detection | Recovery |
|----------|-----------|----------|
| Single repo fails to back up | `backup_failure` alarm | Check logs; fix disk/permissions; rerun task manually. |
| Task does not run at all | `task_not_running` alarm | Verify EventBridge rule + Secrets Manager has a valid PEM. |
| Primary region outage | AWS status / client-side 5xx | Restore from replica bucket in `replica_region`. |
| GitHub App key compromised | Out-of-band | Revoke in App settings, rotate PEM, `put-secret-value` the new one. |
| Accidental S3 delete | S3 object missing | Use S3 versioning: restore the prior non-delete-marker version. |
| Backup corruption | `git bundle verify` fails | Restore from an earlier day's backup (daily prefixes + versioning). |

## Running a Backup On Demand

Useful for verifying a fix without waiting for the next scheduled run:

```bash
CLUSTER="$(terraform output -raw ecs_cluster_name)"
TASK_DEF="$(terraform output -raw task_definition_arn)"
SG="$(terraform output -raw security_group_id)"
SUBNETS='["subnet-abc123","subnet-def456"]'

aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=${SUBNETS},securityGroups=[\"$SG\"],assignPublicIp=DISABLED}"
```

Tail the logs:

```bash
aws logs tail "$(terraform output -raw log_group_name)" --follow
```

## Re-Populating a Wiped Secret

If the Secrets Manager secret is emptied or the secret value is deleted:

```bash
aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw github_app_key_secret_arn)" \
  --secret-string file://github-app.pem
```

The role performing this call must be listed in `github_app_key_secret_writers` (or be the
Terraform admin). Until the secret is populated, the task fails immediately on startup.
