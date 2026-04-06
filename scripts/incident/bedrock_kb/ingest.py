#!/usr/bin/env python3
"""Bedrock Knowledge Base — Data Source, Ingestion, and Validation.

Connects S3 documents to the Knowledge Base and runs indexing:
  1. Create S3 data source on the KB
  2. Start ingestion job (chunking + embedding)
  3. Validate with a test retrieval query

Usage:
    python ingest.py --kb-id <KB_ID> --bucket <BUCKET>
    python ingest.py --kb-id <KB_ID> --bucket <BUCKET> --region us-west-2
    python ingest.py --kb-id <KB_ID> --bucket <BUCKET> --validate-only
"""

import argparse
import json
import sys
import time

import boto3
from botocore.exceptions import ClientError

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

DATA_SOURCE_NAME = "incident-skills-s3"
S3_PREFIX = "skills/"

INGESTION_TIMEOUT_SECONDS = 600
INGESTION_POLL_INTERVAL_SECONDS = 15

VALIDATION_QUERY = "What are the failure modes for AWS Lambda?"


# ------------------------------------------------------------------ #
# Step 1: Create Data Source
# ------------------------------------------------------------------ #

def create_data_source(
    bedrock_client, kb_id: str, bucket_arn: str, region: str
) -> str:
    """Create S3 data source on the Knowledge Base."""

    # Check if data source already exists
    try:
        existing = bedrock_client.list_data_sources(
            knowledgeBaseId=kb_id, maxResults=100
        )
        for ds in existing.get("dataSourceSummaries", []):
            if ds["name"] == DATA_SOURCE_NAME:
                ds_id = ds["dataSourceId"]
                print(f"  Data source already exists: {DATA_SOURCE_NAME} (id={ds_id})")
                return ds_id
    except ClientError:
        pass

    # Create data source with semantic chunking
    try:
        resp = bedrock_client.create_data_source(
            knowledgeBaseId=kb_id,
            name=DATA_SOURCE_NAME,
            description="Incident management skill files from S3",
            dataSourceConfiguration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": bucket_arn,
                    "inclusionPrefixes": [S3_PREFIX],
                },
            },
            vectorIngestionConfiguration={
                "chunkingConfiguration": {
                    "chunkingStrategy": "SEMANTIC",
                    "semanticChunkingConfiguration": {
                        "maxTokens": 512,
                        "bufferSize": 0,
                        "breakpointPercentileThreshold": 95,
                    },
                }
            },
        )
        ds_id = resp["dataSource"]["dataSourceId"]
        print(f"  Created data source: {DATA_SOURCE_NAME} (id={ds_id})")
        print("  Chunking strategy: SEMANTIC (preserves tables/decision trees)")
        return ds_id

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if "Semantic" in str(e) or "SEMANTIC" in str(e):
            # Fall back to fixed-size chunking if semantic not available
            print("  Semantic chunking not available, falling back to FIXED_SIZE")
            resp = bedrock_client.create_data_source(
                knowledgeBaseId=kb_id,
                name=DATA_SOURCE_NAME,
                description="Incident management skill files from S3",
                dataSourceConfiguration={
                    "type": "S3",
                    "s3Configuration": {
                        "bucketArn": bucket_arn,
                        "inclusionPrefixes": [S3_PREFIX],
                    },
                },
                vectorIngestionConfiguration={
                    "chunkingConfiguration": {
                        "chunkingStrategy": "FIXED_SIZE",
                        "fixedSizeChunkingConfiguration": {
                            "maxTokens": 512,
                            "overlapPercentage": 20,
                        },
                    }
                },
            )
            ds_id = resp["dataSource"]["dataSourceId"]
            print(f"  Created data source: {DATA_SOURCE_NAME} (id={ds_id})")
            print("  Chunking strategy: FIXED_SIZE (512 tokens, 20% overlap)")
            return ds_id
        raise


# ------------------------------------------------------------------ #
# Step 2: Start Ingestion Job
# ------------------------------------------------------------------ #

def start_ingestion(bedrock_client, kb_id: str, ds_id: str) -> dict:
    """Start ingestion job and wait for completion."""

    resp = bedrock_client.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
    )

    job_id = resp["ingestionJob"]["ingestionJobId"]
    status = resp["ingestionJob"]["status"]
    print(f"  Started ingestion job: {job_id} (status={status})")

    # Poll for completion
    print(f"  Waiting for ingestion to complete (up to {INGESTION_TIMEOUT_SECONDS}s)...")
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

        docs_scanned = stats.get("numberOfDocumentsScanned", 0)
        docs_indexed = stats.get("numberOfNewDocumentsIndexed", 0) + stats.get(
            "numberOfModifiedDocumentsIndexed", 0
        )
        docs_failed = stats.get("numberOfDocumentsFailed", 0)

        print(
            f"    Status: {status} ({elapsed}s) — "
            f"scanned={docs_scanned}, indexed={docs_indexed}, failed={docs_failed}"
        )

        if status == "COMPLETE":
            return {
                "job_id": job_id,
                "status": status,
                "documents_scanned": docs_scanned,
                "documents_indexed": docs_indexed,
                "documents_failed": docs_failed,
            }

        if status == "FAILED":
            failure_reasons = job.get("failureReasons", [])
            print(f"  ERROR: Ingestion failed")
            for reason in failure_reasons:
                print(f"    Reason: {reason}")
            sys.exit(1)

    print(f"  ERROR: Timed out waiting for ingestion ({INGESTION_TIMEOUT_SECONDS}s)")
    sys.exit(1)


# ------------------------------------------------------------------ #
# Step 3: Validation Query
# ------------------------------------------------------------------ #

def validate_kb(kb_id: str, region: str) -> bool:
    """Run a test retrieval query to validate the KB is working."""

    runtime_client = boto3.client("bedrock-agent-runtime", region_name=region)

    print(f"  Query: \"{VALIDATION_QUERY}\"")

    try:
        resp = runtime_client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": VALIDATION_QUERY},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": 5,
                }
            },
        )
    except ClientError as e:
        print(f"  ERROR: Retrieval failed: {e}")
        return False

    results = resp.get("retrievalResults", [])
    print(f"  Retrieved {len(results)} chunks:")

    lambda_chunks = 0
    for i, result in enumerate(results):
        content = result.get("content", {}).get("text", "")[:200]
        source = result.get("location", {}).get("s3Location", {}).get("uri", "unknown")
        score = result.get("score", 0)

        print(f"\n  Chunk {i + 1} (score={score:.4f}):")
        print(f"    Source: {source}")
        print(f"    Preview: {content}...")

        if "lambda" in source.lower() or "lambda" in content.lower():
            lambda_chunks += 1

    # Validation: at least one chunk should reference Lambda content
    if lambda_chunks > 0:
        print(f"\n  VALIDATION PASSED: {lambda_chunks} chunks contain Lambda content")
        return True
    else:
        print("\n  VALIDATION WARNING: No Lambda-specific chunks found")
        print("  The KB may need time for indexing to propagate, or chunking may need adjustment")
        return False


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="Create data source, run ingestion, and validate Bedrock KB"
    )
    parser.add_argument("--kb-id", required=True, help="Knowledge Base ID from setup_kb.py")
    parser.add_argument("--bucket", required=True, help="S3 bucket name with skill files")
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip ingestion, only run validation query",
    )
    args = parser.parse_args()

    bucket_arn = f"arn:aws:s3:::{args.bucket}"

    print("=" * 60)
    print("Bedrock KB — Data Source & Ingestion")
    print("=" * 60)
    print(f"\nKB ID:  {args.kb_id}")
    print(f"Bucket: {args.bucket}")
    print(f"Region: {args.region}")

    if args.validate_only:
        print("\n[VALIDATE ONLY] Skipping data source and ingestion")
        print("\nStep 3: Validation Query")
        validate_kb(args.kb_id, args.region)
        return

    bedrock_client = boto3.client("bedrock-agent", region_name=args.region)

    # Step 1: Data Source
    print("\nStep 1: Create Data Source")
    ds_id = create_data_source(bedrock_client, args.kb_id, bucket_arn, args.region)

    # Step 2: Ingestion
    print("\nStep 2: Start Ingestion Job")
    result = start_ingestion(bedrock_client, args.kb_id, ds_id)

    # Step 3: Validation
    print("\nStep 3: Validation Query")
    validate_kb(args.kb_id, args.region)

    # Output
    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)
    print(f"\nJob ID:      {result['job_id']}")
    print(f"Scanned:     {result['documents_scanned']} documents")
    print(f"Indexed:     {result['documents_indexed']} documents")
    print(f"Failed:      {result['documents_failed']} documents")
    print(f"\nKB is ready for RetrieveAndGenerate queries")

    return result


if __name__ == "__main__":
    main()
