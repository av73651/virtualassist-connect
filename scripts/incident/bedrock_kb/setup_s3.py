#!/usr/bin/env python3
"""S3 Document Store for Bedrock Knowledge Base.

Creates a versioned S3 bucket and uploads incident management skill files
as the knowledge source for the Bedrock KB.

Usage:
    python setup_s3.py                          # Create bucket + upload files
    python setup_s3.py --region us-west-2       # Specify region
    python setup_s3.py --stage prod             # Specify stage
    python setup_s3.py --dry-run                # Show what would happen
"""

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

SKILLS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "skills", "definitions"
)
SKILL_FILE_PREFIX = "incident-management"
S3_PREFIX = "skills/"
LIFECYCLE_NONCURRENT_DAYS = 90


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _get_account_id() -> str:
    """Get AWS account ID from STS."""
    return boto3.client("sts").get_caller_identity()["Account"]


def _get_git_sha() -> str:
    """Get current git SHA (short) or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _bucket_name(account_id: str, region: str) -> str:
    """Generate globally unique bucket name."""
    return f"virtualassist-incident-kb-{account_id}-{region}"


def _find_skill_files() -> list[str]:
    """Find all incident-management*.md files in skills/definitions/."""
    skills_path = os.path.abspath(SKILLS_DIR)
    if not os.path.isdir(skills_path):
        print(f"ERROR: Skills directory not found: {skills_path}")
        sys.exit(1)

    files = sorted(
        f for f in os.listdir(skills_path)
        if f.startswith(SKILL_FILE_PREFIX) and f.endswith(".md")
    )
    return [os.path.join(skills_path, f) for f in files]


def _file_md5(filepath: str) -> str:
    """Compute MD5 hex digest of a file."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _s3_etag(s3_client, bucket: str, key: str) -> str | None:
    """Get ETag of current S3 object version (stripped of quotes), or None."""
    try:
        resp = s3_client.head_object(Bucket=bucket, Key=key)
        return resp["ETag"].strip('"')
    except ClientError:
        return None


# ------------------------------------------------------------------ #
# Core Operations
# ------------------------------------------------------------------ #

def create_bucket(s3_client, bucket: str, region: str) -> bool:
    """Create S3 bucket with versioning and lifecycle. Idempotent."""
    try:
        # Create bucket
        create_params = {"Bucket": bucket}
        if region != "us-east-1":
            create_params["CreateBucketConfiguration"] = {
                "LocationConstraint": region
            }

        s3_client.create_bucket(**create_params)
        print(f"  Created bucket: {bucket}")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"  Bucket already exists: {bucket}")
        else:
            raise

    # Enable versioning
    s3_client.put_bucket_versioning(
        Bucket=bucket,
        VersioningConfiguration={"Status": "Enabled"},
    )
    print("  Versioning: ENABLED")

    # Block public access
    s3_client.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print("  Public access: BLOCKED")

    # Lifecycle rule: expire noncurrent versions
    s3_client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-noncurrent-skill-versions",
                    "Status": "Enabled",
                    "Filter": {"Prefix": S3_PREFIX},
                    "NoncurrentVersionExpiration": {
                        "NoncurrentDays": LIFECYCLE_NONCURRENT_DAYS,
                    },
                }
            ]
        },
    )
    print(f"  Lifecycle: noncurrent versions expire after {LIFECYCLE_NONCURRENT_DAYS} days")

    return True


def upload_files(s3_client, bucket: str, skill_files: list[str], dry_run: bool = False) -> dict:
    """Upload skill files to S3. Only uploads if content changed.

    Returns dict of {filename: {"status": "uploaded"|"unchanged", "version_id": ...}}."""
    git_sha = _get_git_sha()
    now = datetime.now(timezone.utc).isoformat()
    results = {}

    for filepath in skill_files:
        filename = os.path.basename(filepath)
        s3_key = f"{S3_PREFIX}{filename}"
        local_md5 = _file_md5(filepath)

        # Check if content changed
        remote_etag = _s3_etag(s3_client, bucket, s3_key)
        if remote_etag == local_md5:
            print(f"  {filename}: unchanged (skipped)")
            results[filename] = {"status": "unchanged", "version_id": None}
            continue

        if dry_run:
            print(f"  {filename}: would upload ({local_md5[:8]}...)")
            results[filename] = {"status": "dry-run", "version_id": None}
            continue

        # Upload with metadata tags
        with open(filepath, "rb") as f:
            resp = s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=f.read(),
                ContentType="text/markdown",
                Metadata={
                    "git-sha": git_sha,
                    "uploaded-at": now,
                    "source": f"skills/definitions/{filename}",
                },
            )

        version_id = resp.get("VersionId", "none")
        print(f"  {filename}: uploaded (version={version_id[:12]}...)")
        results[filename] = {"status": "uploaded", "version_id": version_id}

    # Tag objects with git SHA
    for filepath in skill_files:
        filename = os.path.basename(filepath)
        s3_key = f"{S3_PREFIX}{filename}"
        if results.get(filename, {}).get("status") == "uploaded":
            try:
                s3_client.put_object_tagging(
                    Bucket=bucket,
                    Key=s3_key,
                    Tagging={
                        "TagSet": [
                            {"Key": "git-sha", "Value": git_sha},
                            {"Key": "uploaded-at", "Value": now},
                        ]
                    },
                )
            except ClientError:
                pass  # Tagging is best-effort

    return results


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="Create S3 document store for Bedrock Knowledge Base"
    )
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    parser.add_argument("--stage", default="dev", help="Environment stage")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = parser.parse_args()

    print("=" * 60)
    print("Bedrock KB — S3 Document Store Setup")
    print("=" * 60)

    # Discover skill files
    skill_files = _find_skill_files()
    print(f"\nFound {len(skill_files)} skill files:")
    for f in skill_files:
        size_kb = os.path.getsize(f) / 1024
        print(f"  {os.path.basename(f)} ({size_kb:.1f} KB)")

    # Resolve bucket name
    account_id = _get_account_id()
    bucket = _bucket_name(account_id, args.region)
    print(f"\nBucket: {bucket}")

    # Create bucket
    s3_client = boto3.client("s3", region_name=args.region)

    if args.dry_run:
        print("\n[DRY RUN] Would create/verify bucket and upload files")
    else:
        print("\nStep 1: Create/verify bucket")
        create_bucket(s3_client, bucket, args.region)

    # Upload files
    print(f"\nStep 2: Upload skill files to s3://{bucket}/{S3_PREFIX}")
    results = upload_files(s3_client, bucket, skill_files, dry_run=args.dry_run)

    # Summary
    uploaded = sum(1 for r in results.values() if r["status"] == "uploaded")
    unchanged = sum(1 for r in results.values() if r["status"] == "unchanged")

    print(f"\nSummary: {uploaded} uploaded, {unchanged} unchanged, {len(skill_files)} total")
    print(f"\nBucket ARN: arn:aws:s3:::{bucket}")
    print(f"S3 URI: s3://{bucket}/{S3_PREFIX}")
    print(f"Git SHA: {_get_git_sha()}")

    return {"bucket": bucket, "region": args.region, "files_uploaded": uploaded}


if __name__ == "__main__":
    main()
