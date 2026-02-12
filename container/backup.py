#!/usr/bin/env python3
"""
GitHub organization backup runner.

Clones all repositories accessible to a GitHub App installation,
creates git bundles, and uploads them to S3.

Environment variables (set by ECS task definition):
    GITHUB_APP_ID              - GitHub App ID
    GITHUB_APP_INSTALLATION_ID - Installation ID on the target org
    GITHUB_APP_KEY_SECRET_ARN  - Secrets Manager ARN for the private key
    S3_BUCKET                  - Target S3 bucket name
    AWS_DEFAULT_REGION         - AWS region (auto-set by ECS)
"""
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import boto3
import jwt
import requests
from infrahouse_core.aws import Secret
from infrahouse_core.logging import setup_logging

LOG = logging.getLogger(__name__)
setup_logging(LOG)

# ── Configuration ───────────────────────────────────────────────

GITHUB_APP_ID = os.environ["GITHUB_APP_ID"]
GITHUB_APP_INSTALLATION_ID = os.environ["GITHUB_APP_INSTALLATION_ID"]
GITHUB_APP_KEY_SECRET_ARN = os.environ["GITHUB_APP_KEY_SECRET_ARN"]
S3_BUCKET = os.environ["S3_BUCKET"]
GITHUB_API_BASE = "https://api.github.com"

# Token lifetime is 1 hour; refresh when less than 5 minutes remain
TOKEN_REFRESH_THRESHOLD_SECONDS = 300


# ── AWS helpers ─────────────────────────────────────────────────


class _UploadProgress:
    """Callback for boto3 upload_file() to log progress on large uploads."""

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._size = os.path.getsize(filepath)
        self._seen = 0

    def __call__(self, bytes_transferred: int) -> None:
        self._seen += bytes_transferred
        pct = (self._seen / self._size) * 100 if self._size else 100
        LOG.info(
            "Upload progress: %s — %.1f%% (%d / %d bytes)",
            self._filepath,
            pct,
            self._seen,
            self._size,
        )


# Log upload progress for files larger than 100 MiB
_PROGRESS_LOG_THRESHOLD = 100 * 1024 * 1024


def upload_to_s3(
    local_path: str,
    bucket: str,
    s3_key: str,
) -> None:
    """
    Upload a local file to S3.

    For files larger than 100 MiB, logs upload progress via
    a boto3 transfer callback.

    :param local_path: Path to the local file.
    :param bucket: S3 bucket name.
    :param s3_key: S3 object key.
    """
    file_size = os.path.getsize(local_path)
    LOG.info(
        "Uploading %s (%d bytes) -> s3://%s/%s",
        local_path,
        file_size,
        bucket,
        s3_key,
    )
    client = boto3.client("s3")
    callback = (
        _UploadProgress(local_path) if file_size >= _PROGRESS_LOG_THRESHOLD else None
    )
    client.upload_file(local_path, bucket, s3_key, Callback=callback)


def publish_metrics(success_count: int, failure_count: int) -> None:
    """
    Publish backup result metrics to CloudWatch.

    :param success_count: Number of repos backed up successfully.
    :param failure_count: Number of repos that failed.
    """
    client = boto3.client("cloudwatch")
    client.put_metric_data(
        Namespace="GitHubBackup",
        MetricData=[
            {
                "MetricName": "BackupSuccess",
                "Value": success_count,
                "Unit": "Count",
            },
            {
                "MetricName": "BackupFailure",
                "Value": failure_count,
                "Unit": "Count",
            },
        ],
    )


# ── GitHub App authentication ───────────────────────────────────


def create_jwt(app_id: str, private_key: str) -> str:
    """
    Create a JWT for GitHub App authentication.

    :param app_id: The GitHub App ID.
    :param private_key: The PEM-encoded private key.
    :return: Encoded JWT string valid for 10 minutes.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # issued at (60s in the past for clock skew)
        "exp": now + 600,  # expires in 10 minutes
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_token(
    jwt_token: str,
    installation_id: str,
) -> Tuple[str, float]:
    """
    Exchange a JWT for an installation access token.

    :param jwt_token: JWT for the GitHub App.
    :param installation_id: Installation ID on the target org.
    :return: Tuple of (access_token, expiry_timestamp).
    """
    url = f"{GITHUB_API_BASE}/app/installations/" f"{installation_id}/access_tokens"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    token = data["token"]
    expires_at = data["expires_at"]  # ISO 8601
    expiry_ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
    return token, expiry_ts


class TokenManager:
    """
    Manages GitHub App installation token lifecycle.

    Automatically refreshes the token when it is close to expiry.
    """

    def __init__(self, app_id: str, private_key: str, installation_id: str):
        """
        Initialize the TokenManager.

        :param app_id: GitHub App ID.
        :param private_key: PEM-encoded private key.
        :param installation_id: Installation ID on the target org.
        """
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._token: Optional[str] = None
        self._expiry: float = 0

    @property
    def token(self) -> str:
        """
        Get a valid installation token, refreshing if necessary.

        :return: A valid GitHub installation access token.
        """
        if self._needs_refresh():
            self._refresh()
        return self._token

    def _needs_refresh(self) -> bool:
        """
        Check whether the token needs refreshing.

        :return: True if the token is missing or close to expiry.
        """
        if self._token is None:
            return True
        return time.time() > (self._expiry - TOKEN_REFRESH_THRESHOLD_SECONDS)

    def _refresh(self) -> None:
        """Refresh the installation token."""
        LOG.info("Refreshing GitHub installation token")
        jwt_token = create_jwt(self._app_id, self._private_key)
        self._token, self._expiry = get_installation_token(
            jwt_token, self._installation_id
        )


# ── GitHub API helpers ──────────────────────────────────────────


def list_repositories(token: str) -> List[Dict[str, Any]]:
    """
    List all repositories accessible to the installation.

    Paginates through all pages automatically.

    :param token: GitHub installation access token.
    :return: List of repository dicts from the GitHub API.
    """
    repos: List[Dict[str, Any]] = []
    url = f"{GITHUB_API_BASE}/installation/repositories"
    params: Dict[str, Any] = {"per_page": 100}

    while url:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        repos.extend(data.get("repositories", []))

        # Follow pagination via Link header
        url = None
        params = {}
        link_header = response.headers.get("Link", "")
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    LOG.info("Found %d repositories", len(repos))
    return repos


# ── Git operations ──────────────────────────────────────────────


def clone_mirror(
    repo: Dict[str, Any],
    token: str,
    dest_dir: str,
) -> str:
    """
    Clone a repository with --mirror into dest_dir.

    Uses GIT_ASKPASS to supply credentials so that the token never
    appears in command-line arguments, exception tracebacks, or logs.

    :param repo: Repository dict from GitHub API.
    :param token: GitHub installation access token.
    :param dest_dir: Directory to clone into.
    :return: Path to the cloned mirror directory.
    """
    full_name = repo["full_name"]
    clone_url = f"https://github.com/{full_name}.git"
    mirror_dir = os.path.join(dest_dir, "mirror.git")

    # Write a temporary GIT_ASKPASS script that provides the token.
    # Git calls this script with a prompt like "Username for ..." or
    # "Password for ..."; we return the appropriate credential.
    #
    # Why GIT_ASKPASS over alternatives:
    #  - Environment variables are visible via /proc/<pid>/environ.
    #  - Embedding the token in the clone URL leaks it in logs and
    #    error messages.
    #  - GIT_ASKPASS keeps the token out of the process table and
    #    git's own output.  The file is short-lived and cleaned up
    #    in the finally block; Fargate's ephemeral storage provides
    #    an additional safety net.
    askpass_path = os.path.join(dest_dir, "git-askpass.sh")
    with open(askpass_path, "w") as fp:
        fp.write("#!/bin/sh\n")
        fp.write('case "$1" in\n')
        fp.write('  Username*) echo "x-access-token" ;;\n')
        fp.write(f'  Password*) echo "{token}" ;;\n')
        fp.write("esac\n")
    os.chmod(askpass_path, 0o700)

    env = {**os.environ, "GIT_ASKPASS": askpass_path, "GIT_TERMINAL_PROMPT": "0"}

    LOG.info("Cloning %s (mirror)", full_name)
    try:
        subprocess.run(
            ["git", "clone", "--mirror", clone_url, mirror_dir],
            check=True,
            capture_output=True,
            timeout=3600,
            env=env,
        )
    finally:
        os.remove(askpass_path)
    return mirror_dir


def create_bundle(
    mirror_dir: str,
    bundle_path: str,
) -> None:
    """
    Create a git bundle from a mirror clone.

    :param mirror_dir: Path to the mirror .git directory.
    :param bundle_path: Output path for the bundle file.
    """
    LOG.info("Creating bundle %s", bundle_path)
    subprocess.run(
        ["git", "bundle", "create", bundle_path, "--all"],
        cwd=mirror_dir,
        check=True,
        capture_output=True,
        timeout=3600,
    )


# ── Main ────────────────────────────────────────────────────────


def main() -> None:
    """
    Run the GitHub backup process.

    1. Authenticate via GitHub App.
    2. List all accessible repositories.
    3. Clone, bundle, and upload each repo to S3.
    4. Write a manifest and publish metrics.

    Any exception crashes the process.  The "task not running"
    CloudWatch alarm (treat_missing_data = "breaching") fires
    when no BackupSuccess metric is published.
    """
    LOG.info("Starting GitHub backup")

    # 1. Read private key from Secrets Manager
    private_key = Secret(GITHUB_APP_KEY_SECRET_ARN).value

    # 2. Set up token manager (handles refresh automatically)
    token_mgr = TokenManager(GITHUB_APP_ID, private_key, GITHUB_APP_INSTALLATION_ID)

    # 3. List all repositories
    repos = list_repositories(token_mgr.token)

    # 4. Back up each repo
    # Any exception aborts the run — no metrics are published,
    # which triggers the "task not running" CloudWatch alarm
    # (treat_missing_data = "breaching").
    results: List[Dict[str, Any]] = []
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for repo in repos:
        full_name = repo["full_name"]
        org_name, repo_name = full_name.split("/", 1)
        tmp_dir = tempfile.mkdtemp(prefix="ghbackup-")

        try:
            # Use fresh token (auto-refreshes if near expiry)
            current_token = token_mgr.token

            # Clone
            mirror_dir = clone_mirror(repo, current_token, tmp_dir)

            # Bundle
            bundle_path = os.path.join(tmp_dir, f"{repo_name}.bundle")
            create_bundle(mirror_dir, bundle_path)

            # Upload
            s3_key = f"github-backup/{date_prefix}/{org_name}/{repo_name}.bundle"
            upload_to_s3(bundle_path, S3_BUCKET, s3_key)

            bundle_size = os.path.getsize(bundle_path)
            results.append(
                {
                    "repo": full_name,
                    "size_bytes": bundle_size,
                    "s3_key": s3_key,
                }
            )
            LOG.info("Backed up %s (%d bytes)", full_name, bundle_size)

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # 5. Write manifest
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": date_prefix,
        "total_repos": len(repos),
        "success_count": len(results),
        "repos": results,
    }
    manifest_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    try:
        json.dump(manifest, manifest_tmp, indent=2)
        manifest_tmp.close()
        upload_to_s3(
            manifest_tmp.name,
            S3_BUCKET,
            f"github-backup/{date_prefix}/manifest.json",
        )
    finally:
        os.unlink(manifest_tmp.name)

    # 6. Publish CloudWatch metrics
    publish_metrics(len(results), 0)

    # 7. Report
    LOG.info("Backup complete: %d repos backed up", len(results))


if __name__ == "__main__":
    main()
