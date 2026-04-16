# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## First Steps

**Your first tool call in this repository MUST be reading .claude/CODING_STANDARD.md.
Do not read any other files, search, or take any actions until you have read it.**
This contains InfraHouse's comprehensive coding standards for Terraform, Python, and general formatting rules.

## What This Module Does

Terraform module that backs up all repositories in a GitHub organization to S3 using an ECS Fargate scheduled
task. A Python container (`container/backup.py`) authenticates via a customer-owned GitHub App, clones every
repo with `git bundle`, and uploads bundles plus a manifest to S3. Cross-region replication provides DR.

## Build and Development Commands

```bash
make bootstrap          # Install Python deps + git hooks
make test               # Run pytest (creates real AWS infra in us-west-2)
make test-keep          # Run tests, keep infra after for debugging
make test-clean         # Run tests with full cleanup
make format             # terraform fmt -recursive + black on tests/ and container/ (also: make fmt)
make lint               # terraform fmt -check + black --check on tests/ and container/
make clean              # Remove caches, .terraform dirs, lock files
```

Run a single test (either form works):
```bash
TEST_FILTER=test_module make test              # Makefile-native
TEST_SELECTOR=tests/test_module.py make test   # target by path
pytest -xvvs -k "test_module" tests/           # direct pytest
```

Tests assume an AWS role (`arn:aws:iam::303467602807:role/github-backup-tester`) and deploy real
infrastructure. Override with `TEST_ROLE` and `TEST_REGION` env vars. The test also reads a control GitHub
App PEM from a Secrets Manager secret in `us-west-1` within the tester account — outside contributors
cannot run `make test` without providing their own equivalent.

## Commit Conventions

Commits are validated by a `hooks/commit-msg` hook enforcing **Conventional Commits**:
```
feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|security[(!)](scope): description
```

The pre-commit hook runs `terraform fmt -check`, `terraform-docs` (auto-stages README.md changes), and
verifies all files end with a newline.

## Versioning and Releases

Version is tracked in `.bumpversion.cfg` (currently 2.0.1), mirrored in `README.md` and `locals.tf`.
Release via `make release-patch|minor|major` which updates CHANGELOG.md with `git-cliff`, bumps version,
and pushes tags.

## Architecture

**Terraform resources** (root `.tf` files): ECS cluster + task definition (`ecs.tf`), EventBridge schedule
(`eventbridge.tf`), S3 primary bucket + cross-region replica (`s3.tf`, `s3_replication.tf`), IAM roles for
execution/task/eventbridge/replication (`iam.tf`), CloudWatch logs + alarms (`cloudwatch.tf`), Secrets
Manager for GitHub App key (`secret.tf`), security group (`security_group.tf`), SNS for alarm
notifications (`sns.tf`).

**Cross-region replication** uses AWS provider v6 and deliberately avoids aliased providers — the replica
bucket is managed via provider-v6 `region` arguments on each resource. Do not reintroduce
`provider = aws.replica` aliases when editing `s3_replication.tf`.

**Post-deploy manual step**: after `terraform apply`, the GitHub App PEM private key must be written into
the Secrets Manager secret whose ARN is published as the `github_app_key_secret_arn` output. Until that
secret is populated, the ECS task cannot authenticate to GitHub. The test harness does this automatically;
consumers do it once by hand (or via their own deploy tooling).

**Container** (`container/`): Python script (`backup.py`) runs as the ECS task. Uses `TokenManager` for
auto-refreshing GitHub App installation tokens. Clones repos via `GIT_ASKPASS` (avoids leaking tokens),
creates git bundles, uploads to S3, writes a `manifest.json`, and publishes CloudWatch metrics. Any
failure crashes the process; the "task not running" alarm (treat_missing_data=breaching) fires when no
BackupSuccess metric is published.

**Test harness** (`tests/`, `test_data/main/`): Uses `pytest-infrahouse` which wraps Terraform
apply/destroy. The test deploys the module, builds and pushes the container to a test ECR repo, populates
the GitHub App secret from a control secret in us-west-1, runs the ECS task, waits for completion, and
verifies `.bundle` files + `manifest.json` exist in S3.

## Key Dependencies

- Terraform ~> 1.5, AWS provider ~> 6.0
- Python: `pytest-infrahouse`, `infrahouse-core` (test + container runtime)
- Container: `PyJWT`, `requests`, `boto3`, `infrahouse-core`
- Uses InfraHouse registry modules: `infrahouse/s3-bucket/aws`, `infrahouse/secret/aws`
