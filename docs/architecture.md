# Architecture

![Architecture](assets/architecture.svg)

## How It Works

On every EventBridge tick the module runs a one-shot Fargate task that backs up every GitHub repo
the App can see, then exits.

### Runtime flow (per invocation)

1. **EventBridge** fires per `schedule_expression` and invokes `RunTask` on the ECS cluster.
2. **Fargate task** starts in the customer VPC and reads the GitHub App PEM from Secrets Manager.
3. The container mints a signed **JWT**, exchanges it for a short-lived GitHub **installation
   token**, and refreshes that token as it ages (`TokenManager`).
4. It lists every repository the App has access to via the GitHub REST API.
5. For each repo it runs `git clone --mirror` (credentials supplied via `GIT_ASKPASS` so the
   token never appears in the process table or shell history).
6. It runs `git bundle create <repo>.bundle --all` to produce a single self-contained file.
7. It uploads each bundle to the **S3 primary bucket** under `github-backup/<YYYY-MM-DD>/<org>/`.
8. It writes a `manifest.json` with repo metadata (name, default branch, SHA, size).
9. It emits `BackupSuccess` / `BackupFailure` CloudWatch metrics under namespace `GitHubBackup`.
10. **S3 Cross-Region Replication** asynchronously copies the new objects to the replica bucket.
11. Any failure crashes the container (non-zero exit). Alarms fire on failure or on missing
    success metrics.

### Data layout in S3

```
github-backup/
  2026-04-16/
    manifest.json
    your-org/
      repo-a.bundle
      repo-b.bundle
```

Bundles are immutable once uploaded. S3 versioning + lifecycle (`backup_retention_days`) controls
how long history is retained.

## Components

| Component | Purpose |
|-----------|---------|
| **ECS Cluster** (`aws_ecs_cluster.backup`) | Fargate cluster, Container Insights enabled. |
| **ECS Task Definition** (`aws_ecs_task_definition.backup`) | Runs `container/backup.py` on Fargate. |
| **EventBridge Rule** (`aws_cloudwatch_event_rule.backup`) | Scheduler that triggers the task. |
| **S3 Primary Bucket** (via `infrahouse/s3-bucket/aws`) | Stores bundles + manifest. Versioned. |
| **S3 Replica Bucket** (`aws_s3_bucket.replica`) | CRR target in `replica_region`. |
| **Replication IAM role** | Assumed by S3 service for cross-region replication. |
| **Secrets Manager Secret** (via `infrahouse/secret/aws`) | Holds the GitHub App PEM. |
| **Task IAM role** | Read secret, write S3, publish CloudWatch metrics. |
| **Execution IAM role** | Pull image from ECR, write logs. |
| **EventBridge IAM role** | Allows EventBridge to call `ecs:RunTask` + pass roles. |
| **Security Group** | Egress-only; locks the task down to outbound traffic. |
| **CloudWatch Log Groups** | `/ecs/<service>` (task stdout) + `/aws/ecs/containerinsights/<cluster>/performance`. |
| **CloudWatch Alarms** | `backup_failure`, `task_not_running` (treat_missing_data=breaching). |
| **SNS Topic + Subscriptions** | Email delivery for alarms. |

## Key Design Decisions

- **Fargate, not Lambda** — no 15-minute timeout, no always-on EC2. You pay for the backup window
  only. Large organizations with many repos don't hit wall-clock limits.
- **Customer-owned GitHub App** — no shared credentials from InfraHouse. Installation tokens
  expire in an hour, limiting blast radius if a bundle is leaked with the token still in memory.
- **InfraHouse-published container image** on public ECR — no per-customer build pipeline needed,
  but `image_uri` can be pinned to a SHA for reproducibility.
- **S3 with versioning + lifecycle** — object versioning protects against deletion/overwrite;
  lifecycle handles long-term retention.
- **Cross-region replication via AWS provider v6 per-resource `region`** — deliberately avoids
  aliased providers (`provider = aws.replica`) because consumers don't want to pass a second
  provider. Each replica resource sets `region = var.replica_region` directly.
- **Module-managed secret** (`infrahouse/secret/aws`) — fine-grained resource policy separates
  admin / writers / readers, audit-friendly via CloudTrail.
- **`git bundle`** over tarballs — bundles are a native git format; restore is `git clone repo.bundle`
  with no extra tooling, and they preserve full history, branches, and tags.
- **GIT_ASKPASS** for credentials — the installation token never lands on the command line or in
  the shell history, which tarball-based approaches often leak.

## Disaster Recovery

### RPO and RTO

| Metric | Value | Notes |
|--------|-------|-------|
| **RPO** | Up to the schedule interval (default: 24h) | Worst case is one full `schedule_expression` interval. |
| **RTO** | Minutes per repository | Single-repo restore is seconds. Full-org scales with repo count/size. |

### Backup Storage

Backups live in two buckets:

- **Primary** — in the region where the module is deployed (where the Fargate task runs).
- **Replica** — in `replica_region`, synchronized via S3 Cross-Region Replication.

Both are versioned, so even if a backup is overwritten or deleted, previous versions are retained
per the lifecycle policy.

### Failure Modes the Alarms Catch

| Alarm | Metric | Condition | Catches |
|-------|--------|-----------|---------|
| `backup_failure` | `GitHubBackup/BackupFailure` | sum > 0 / 24h | Repo failed to clone/bundle/upload. |
| `task_not_running` | `GitHubBackup/BackupSuccess` | count < 1 / 24h, missing=breach | Task never ran. |

See [Troubleshooting](troubleshooting.md) for restore procedures and recovery steps.
