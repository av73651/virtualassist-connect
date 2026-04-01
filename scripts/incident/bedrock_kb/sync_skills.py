#!/usr/bin/env python3
"""Bedrock Knowledge Base — Sync, Version, and Rollback.

Handles the document lifecycle for the KB:
  - Re-sync: Upload changed skill files to S3, trigger re-ingestion
  - Rollback: Restore a previous S3 version, trigger re-ingestion
  - Status: Show current versions and ingestion state

Usage:
    python sync_skills.py --kb-id <KB_ID> --bucket <BUCKET>                    # Sync changed files
    python sync_skills.py --kb-id <KB_ID> --bucket <BUCKET> --status           # Show version status
    python sync_skills.py --kb-id <KB_ID> --bucket <BUCKET> --list-versions    # List all versions
    python sync_skills.py --kb-id <KB_ID> --bucket <BUCKET> --rollback-to <VERSION_ID> --file <FILENAME>
"""

import argparse
import hashlib
import os
import subprocess
import sys
import time
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

INGESTION_TIMEOUT_SECONDS = 600
INGESTION_POLL_INTERVAL_SECONDS = 15


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _find_skill_files() -> list[str]:
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
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _s3_etag(s3_client, bucket: str, key: str) -> str | None:
    try:
        resp = s3_client.head_object(Bucket=bucket, Key=key)
        return resp["ETag"].strip('"')
    except ClientError:
        return None


def _find_data_source_id(bedrock_client, kb_id: str) -> str | None:
    """Find the existing data source ID for the KB."""
    try:
        resp = bedrock_client.list_data_sources(knowledgeBaseId=kb_id, maxResults=100)
        for ds in resp.get("dataSourceSummaries", []):
            if ds["name"] == "incident-skills-s3":
                return ds["dataSourceId"]
    except ClientError:
        pass
    return None


# ------------------------------------------------------------------ #
# Sync: Upload changed files + re-ingest
# ------------------------------------------------------------------ #

def sync_files(s3_client, bucket: str, skill_files: list[str]) -> list[str]:
    """Upload changed skill files to S3. Returns list of changed filenames."""
    git_sha = _get_git_sha()
    now = datetime.now(timezone.utc).isoformat()
    changed = []

    for filepath in skill_files:
        filename = os.path.basename(filepath)
        s3_key = f"{S3_PREFIX}{filename}"
        local_md5 = _file_md5(filepath)
        remote_etag = _s3_etag(s3_client, bucket, s3_key)

        if remote_etag == local_md5:
            print(f"  {filename}: unchanged")
            continue

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
        print(f"  {filename}: uploaded (version={version_id[:12]}..., sha={git_sha})")
        changed.append(filename)

        # Tag object
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
            pass

    return changed


def trigger_ingestion(bedrock_client, kb_id: str, ds_id: str) -> bool:
    """Start ingestion job and wait for completion."""
    resp = bedrock_client.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
    )
    job_id = resp["ingestionJob"]["ingestionJobId"]
    print(f"  Ingestion job started: {job_id}")

    elapsed = 0
    while elapsed < INGESTION_TIMEOUT_SECONDS:
        time.sleep(INGESTION_POLL_INTERVAL_SECONDS)
        elapsed += INGESTION_POLL_INTERVAL_SECONDS

        job_resp = bedrock_client.get_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            ingestionJobId=job_id,
        )
        job = job_resp["ingestionJob"]
        status = job["status"]
        stats = job.get("statistics", {})
        scanned = stats.get("numberOfDocumentsScanned", 0)
        indexed = (
            stats.get("numberOfNewDocumentsIndexed", 0)
            + stats.get("numberOfModifiedDocumentsIndexed", 0)
        )
        failed = stats.get("numberOfDocumentsFailed", 0)

        print(f"    {status} ({elapsed}s) — scanned={scanned}, indexed={indexed}, failed={failed}")

        if status == "COMPLETE":
            return True
        if status == "FAILED":
            for reason in job.get("failureReasons", []):
                print(f"    FAILURE: {reason}")
            return False

    print(f"  ERROR: Timed out ({INGESTION_TIMEOUT_SECONDS}s)")
    return False


# ------------------------------------------------------------------ #
# Status: Show current versions
# ------------------------------------------------------------------ #

def show_status(s3_client, bucket: str, skill_files: list[str]) -> None:
    """Show current S3 version status for all skill files."""
    print(f"\n{'Filename':<50} {'S3 ETag':<34} {'Local MD5':<34} {'Match'}")
    print("-" * 130)

    for filepath in skill_files:
        filename = os.path.basename(filepath)
        s3_key = f"{S3_PREFIX}{filename}"
        local_md5 = _file_md5(filepath)
        remote_etag = _s3_etag(s3_client, bucket, s3_key) or "(not in S3)"
        match = "YES" if remote_etag == local_md5 else "NO"
        print(f"  {filename:<48} {remote_etag:<34} {local_md5:<34} {match}")


# ------------------------------------------------------------------ #
# List Versions: Show all S3 object versions
# ------------------------------------------------------------------ #

def list_versions(s3_client, bucket: str) -> None:
    """List all S3 object versions for skill files."""
    try:
        resp = s3_client.list_object_versions(Bucket=bucket, Prefix=S3_PREFIX)
    except ClientError as e:
        print(f"ERROR: {e}")
        return

    versions = resp.get("Versions", [])
    if not versions:
        print("  No versions found")
        return

    # Group by key
    by_key: dict[str, list] = {}
    for v in versions:
        key = v["Key"]
        by_key.setdefault(key, []).append(v)

    for key, vers in sorted(by_key.items()):
        filename = key.replace(S3_PREFIX, "")
        print(f"\n  {filename}:")
        for v in vers:
            version_id = v["VersionId"]
            last_modified = v["LastModified"].strftime("%Y-%m-%d %H:%M:%S UTC")
            is_latest = v.get("IsLatest", False)
            size_kb = v["Size"] / 1024
            marker = " (CURRENT)" if is_latest else ""
            print(f"    {version_id[:20]}...  {last_modified}  {size_kb:.1f}KB{marker}")

            # Try to get git-sha tag
            try:
                tag_resp = s3_client.get_object_tagging(
                    Bucket=bucket, Key=key, VersionId=version_id
                )
                tags = {t["Key"]: t["Value"] for t in tag_resp.get("TagSet", [])}
                if "git-sha" in tags:
                    print(f"      git-sha: {tags['git-sha']}")
            except ClientError:
                pass


# ------------------------------------------------------------------ #
# Rollback: Restore a previous S3 version
# ------------------------------------------------------------------ #

def rollback_file(s3_client, bucket: str, filename: str, target_version_id: str) -> bool:
    """Restore a previous version of a skill file by copying it as the current version."""
    s3_key = f"{S3_PREFIX}{filename}"

    try:
        # Copy the old version as a new current version
        s3_client.copy_object(
            Bucket=bucket,
            Key=s3_key,
            CopySource={
                "Bucket": bucket,
                "Key": s3_key,
                "VersionId": target_version_id,
            },
            MetadataDirective="COPY",
        )
        print(f"  Restored {filename} to version {target_version_id[:20]}...")
        return True
    except ClientError as e:
        print(f"  ERROR: Failed to rollback {filename}: {e}")
        return False


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="Sync, version, and rollback skill files for Bedrock KB"
    )
    parser.add_argument("--kb-id", required=True, help="Knowledge Base ID")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    parser.add_argument("--status", action="store_true", help="Show version status")
    parser.add_argument("--list-versions", action="store_true", help="List all S3 versions")
    parser.add_argument("--rollback-to", help="Version ID to rollback to")
    parser.add_argument("--file", help="Filename to rollback (used with --rollback-to)")
    args = parser.parse_args()

    print("=" * 60)
    print("Bedrock KB — Skill File Sync & Version Management")
    print("=" * 60)
    print(f"\nKB ID:  {args.kb_id}")
    print(f"Bucket: {args.bucket}")
    print(f"Region: {args.region}")

    s3_client = boto3.client("s3", region_name=args.region)
    skill_files = _find_skill_files()

    # Status mode
    if args.status:
        print("\nVersion Status:")
        show_status(s3_client, args.bucket, skill_files)
        return 0

    # List versions mode
    if args.list_versions:
        print("\nAll S3 Versions:")
        list_versions(s3_client, args.bucket)
        return 0

    # Rollback mode
    if args.rollback_to:
        if not args.file:
            print("ERROR: --file is required with --rollback-to")
            return 1

        print(f"\nRollback: {args.file} → version {args.rollback_to[:20]}...")
        if not rollback_file(s3_client, args.bucket, args.file, args.rollback_to):
            return 1

        # Trigger re-ingestion after rollback
        bedrock_client = boto3.client("bedrock-agent", region_name=args.region)
        ds_id = _find_data_source_id(bedrock_client, args.kb_id)
        if ds_id:
            print("\nRe-ingesting after rollback...")
            success = trigger_ingestion(bedrock_client, args.kb_id, ds_id)
            return 0 if success else 1
        else:
            print("  WARNING: No data source found. Run ingest.py first.")
            return 1

    # Default: Sync mode
    print(f"\nSync: Checking {len(skill_files)} skill files...")
    changed = sync_files(s3_client, args.bucket, skill_files)

    if not changed:
        print("\nNo files changed. KB is up to date.")
        return 0

    print(f"\n{len(changed)} file(s) changed: {', '.join(changed)}")

    # Trigger re-ingestion
    bedrock_client = boto3.client("bedrock-agent", region_name=args.region)
    ds_id = _find_data_source_id(bedrock_client, args.kb_id)
    if ds_id:
        print("\nTriggering re-ingestion...")
        success = trigger_ingestion(bedrock_client, args.kb_id, ds_id)
        if success:
            print("\nSync complete. KB updated with latest skill files.")
        return 0 if success else 1
    else:
        print("\n  WARNING: No data source found. Run ingest.py to create data source first.")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
