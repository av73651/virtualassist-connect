#!/usr/bin/env python3
"""Bedrock Knowledge Base — Creation, Vector Store, Embedding.

Creates the full KB infrastructure:
  1. IAM role for Bedrock service
  2. OpenSearch Serverless collection (vector store)
  3. AOSS encryption, network, and data access policies
  4. Bedrock Knowledge Base resource
  5. Vector index on AOSS collection

Usage:
    python setup_kb.py                              # Create KB with defaults
    python setup_kb.py --region us-west-2 --stage dev
    python setup_kb.py --bucket <bucket-name>       # Use existing S3 bucket
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

EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024
VECTOR_INDEX_NAME = "bedrock-knowledge-base-default-index"
VECTOR_FIELD = "bedrock-knowledge-base-default-vector"
TEXT_FIELD = "AMAZON_BEDROCK_TEXT_CHUNK"
METADATA_FIELD = "AMAZON_BEDROCK_METADATA"

AOSS_WAIT_TIMEOUT_SECONDS = 600
AOSS_POLL_INTERVAL_SECONDS = 15


# ------------------------------------------------------------------ #
# Step 1: IAM Role for Bedrock
# ------------------------------------------------------------------ #

def create_bedrock_role(iam_client, role_name: str, bucket_arn: str, account_id: str, region: str) -> str:
    """Create IAM role that Bedrock assumes to access S3 and AOSS."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/*"
                    },
                },
            }
        ],
    }

    try:
        resp = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Bedrock KB role for incident management skill files",
        )
        role_arn = resp["Role"]["Arn"]
        print(f"  Created IAM role: {role_name}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            role_arn = iam_client.get_role(RoleName=role_name)["Role"]["Arn"]
            print(f"  IAM role already exists: {role_name}")
        else:
            raise

    # Attach inline policy: S3 read + AOSS API access + Bedrock embedding
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "S3ReadSkillFiles",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [bucket_arn, f"{bucket_arn}/*"],
            },
            {
                "Sid": "AOSSApiAccess",
                "Effect": "Allow",
                "Action": ["aoss:APIAccessAll"],
                "Resource": [f"arn:aws:aoss:{region}:{account_id}:collection/*"],
            },
            {
                "Sid": "BedrockEmbedding",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel"],
                "Resource": [
                    f"arn:aws:bedrock:{region}::foundation-model/{EMBEDDING_MODEL}"
                ],
            },
        ],
    }

    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName="bedrock-kb-access",
        PolicyDocument=json.dumps(policy),
    )
    print("  Attached inline policy: S3 + AOSS + Bedrock embedding")

    # Wait for IAM propagation
    print("  Waiting 10s for IAM role propagation...")
    time.sleep(10)

    return role_arn


# ------------------------------------------------------------------ #
# Step 2: OpenSearch Serverless Collection
# ------------------------------------------------------------------ #

def create_aoss_policies(aoss_client, collection_name: str, role_arn: str, account_id: str) -> None:
    """Create encryption, network, and data access policies for AOSS collection."""

    # Encryption policy (required before collection creation)
    encryption_policy = {
        "Rules": [{"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]}],
        "AWSOwnedKey": True,
    }
    try:
        aoss_client.create_security_policy(
            name=f"{collection_name}-enc",
            type="encryption",
            policy=json.dumps(encryption_policy),
        )
        print(f"  Created encryption policy: {collection_name}-enc")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print(f"  Encryption policy already exists: {collection_name}-enc")
        else:
            raise

    # Network policy (public access for POC)
    network_policy = [
        {
            "Rules": [
                {"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]},
                {"ResourceType": "dashboard", "Resource": [f"collection/{collection_name}"]},
            ],
            "AllowFromPublic": True,
        }
    ]
    try:
        aoss_client.create_security_policy(
            name=f"{collection_name}-net",
            type="network",
            policy=json.dumps(network_policy),
        )
        print(f"  Created network policy: {collection_name}-net (public — POC only)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print(f"  Network policy already exists: {collection_name}-net")
        else:
            raise

    # Data access policy — allows Bedrock role + current caller to index/read
    # Convert STS assumed-role ARN to IAM role ARN for AOSS compatibility
    caller_arn = boto3.client("sts").get_caller_identity()["Arn"]
    if ":assumed-role/" in caller_arn:
        # arn:aws:sts::ACCT:assumed-role/ROLE/SESSION -> arn:aws:iam::ACCT:role/ROLE
        parts = caller_arn.split("/")
        role_name = parts[1] if len(parts) >= 2 else parts[0]
        caller_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    data_access_policy = [
        {
            "Rules": [
                {
                    "ResourceType": "index",
                    "Resource": [f"index/{collection_name}/*"],
                    "Permission": [
                        "aoss:CreateIndex",
                        "aoss:UpdateIndex",
                        "aoss:DescribeIndex",
                        "aoss:ReadDocument",
                        "aoss:WriteDocument",
                    ],
                },
                {
                    "ResourceType": "collection",
                    "Resource": [f"collection/{collection_name}"],
                    "Permission": [
                        "aoss:CreateCollectionItems",
                        "aoss:UpdateCollectionItems",
                        "aoss:DescribeCollectionItems",
                    ],
                },
            ],
            "Principal": [role_arn, caller_arn],
        }
    ]
    try:
        aoss_client.create_access_policy(
            name=f"{collection_name}-data",
            type="data",
            policy=json.dumps(data_access_policy),
        )
        print(f"  Created data access policy: {collection_name}-data")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            # Fetch current policy version, then try update
            try:
                existing_policy = aoss_client.get_access_policy(
                    name=f"{collection_name}-data", type="data"
                )
                current_version = existing_policy["accessPolicyDetail"]["policyVersion"]
                aoss_client.update_access_policy(
                    name=f"{collection_name}-data",
                    type="data",
                    policyVersion=current_version,
                    policy=json.dumps(data_access_policy),
                )
                print(f"  Data access policy already exists: {collection_name}-data (updated)")
            except ClientError as update_err:
                if "No changes detected" in str(update_err):
                    print(f"  Data access policy already exists: {collection_name}-data (unchanged)")
                else:
                    raise
        else:
            raise


def create_aoss_collection(aoss_client, collection_name: str) -> dict:
    """Create OpenSearch Serverless collection and wait for ACTIVE status."""

    # Check if collection already exists
    try:
        existing = aoss_client.batch_get_collection(names=[collection_name])
        details = existing.get("collectionDetails", [])
        if details and details[0].get("status") == "ACTIVE":
            print(f"  Collection already exists and ACTIVE: {collection_name}")
            return {
                "id": details[0]["id"],
                "arn": details[0]["arn"],
                "endpoint": details[0]["collectionEndpoint"],
            }
    except (ClientError, KeyError, IndexError):
        pass

    # Create collection
    resp = aoss_client.create_collection(
        name=collection_name,
        type="VECTORSEARCH",
        description="Vector store for incident management Bedrock KB",
    )
    collection_id = resp["createCollectionDetail"]["id"]
    print(f"  Created AOSS collection: {collection_name} (id={collection_id})")

    # Wait for ACTIVE
    print(f"  Waiting for collection to become ACTIVE (up to {AOSS_WAIT_TIMEOUT_SECONDS}s)...")
    elapsed = 0
    while elapsed < AOSS_WAIT_TIMEOUT_SECONDS:
        time.sleep(AOSS_POLL_INTERVAL_SECONDS)
        elapsed += AOSS_POLL_INTERVAL_SECONDS

        status_resp = aoss_client.batch_get_collection(ids=[collection_id])
        details = status_resp.get("collectionDetails", [])
        if details:
            status = details[0].get("status", "UNKNOWN")
            print(f"    Status: {status} ({elapsed}s)")
            if status == "ACTIVE":
                return {
                    "id": details[0]["id"],
                    "arn": details[0]["arn"],
                    "endpoint": details[0]["collectionEndpoint"],
                }
            if status == "FAILED":
                print("  ERROR: Collection creation failed")
                sys.exit(1)

    print(f"  ERROR: Timed out waiting for collection ({AOSS_WAIT_TIMEOUT_SECONDS}s)")
    sys.exit(1)


# ------------------------------------------------------------------ #
# Step 3: Vector Index on AOSS
# ------------------------------------------------------------------ #

def create_vector_index(collection_endpoint: str, region: str) -> None:
    """Create the vector index on the AOSS collection using opensearch-py."""
    try:
        from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
    except ImportError:
        try:
            from opensearchpy import OpenSearch, RequestsHttpConnection
            from requests_aws4auth import AWS4Auth
            AWSV4SignerAuth = None
        except ImportError:
            print("  WARNING: opensearch-py not installed. Skipping index creation.")
            print("  Install with: pip install opensearch-py requests-aws4auth")
            print("  Bedrock will auto-create the index during first ingestion.")
            return

    credentials = boto3.Session().get_credentials()
    if AWSV4SignerAuth is not None:
        auth = AWSV4SignerAuth(credentials, region, "aoss")
    else:
        creds = credentials.get_frozen_credentials()
        auth = AWS4Auth(creds.access_key, creds.secret_key, region, "aoss",
                        session_token=creds.token)

    host = collection_endpoint.replace("https://", "")
    client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )

    # Check if index exists
    if client.indices.exists(index=VECTOR_INDEX_NAME):
        print(f"  Vector index already exists: {VECTOR_INDEX_NAME}")
        return

    # Create index with knn mapping
    index_body = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 512,
            }
        },
        "mappings": {
            "properties": {
                VECTOR_FIELD: {
                    "type": "knn_vector",
                    "dimension": EMBEDDING_DIMENSIONS,
                    "method": {
                        "engine": "faiss",
                        "space_type": "l2",
                        "name": "hnsw",
                        "parameters": {"ef_construction": 512, "m": 16},
                    },
                },
                TEXT_FIELD: {"type": "text"},
                METADATA_FIELD: {"type": "text", "index": False},
            }
        },
    }

    client.indices.create(index=VECTOR_INDEX_NAME, body=index_body)
    print(f"  Created vector index: {VECTOR_INDEX_NAME} ({EMBEDDING_DIMENSIONS} dims)")


# ------------------------------------------------------------------ #
# Step 4: Bedrock Knowledge Base
# ------------------------------------------------------------------ #

def create_knowledge_base(
    bedrock_client, kb_name: str, role_arn: str, collection_arn: str, region: str
) -> str:
    """Create Bedrock Knowledge Base pointing to the AOSS collection."""

    # Check if KB already exists
    try:
        existing = bedrock_client.list_knowledge_bases(maxResults=100)
        for kb in existing.get("knowledgeBaseSummaries", []):
            if kb["name"] == kb_name and kb["status"] == "ACTIVE":
                kb_id = kb["knowledgeBaseId"]
                print(f"  Knowledge Base already exists: {kb_name} (id={kb_id})")
                return kb_id
    except ClientError:
        pass

    resp = bedrock_client.create_knowledge_base(
        name=kb_name,
        description="Incident management skill files for AI-powered triage classification",
        roleArn=role_arn,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": f"arn:aws:bedrock:{region}::foundation-model/{EMBEDDING_MODEL}",
            },
        },
        storageConfiguration={
            "type": "OPENSEARCH_SERVERLESS",
            "opensearchServerlessConfiguration": {
                "collectionArn": collection_arn,
                "vectorIndexName": VECTOR_INDEX_NAME,
                "fieldMapping": {
                    "vectorField": VECTOR_FIELD,
                    "textField": TEXT_FIELD,
                    "metadataField": METADATA_FIELD,
                },
            },
        },
    )

    kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
    status = resp["knowledgeBase"]["status"]
    print(f"  Created Knowledge Base: {kb_name} (id={kb_id}, status={status})")

    # Wait for ACTIVE
    if status != "ACTIVE":
        print("  Waiting for KB to become ACTIVE...")
        for _ in range(20):
            time.sleep(5)
            kb = bedrock_client.get_knowledge_base(knowledgeBaseId=kb_id)
            status = kb["knowledgeBase"]["status"]
            if status == "ACTIVE":
                break
        print(f"  KB status: {status}")

    return kb_id


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="Create Bedrock Knowledge Base with OpenSearch Serverless vector store"
    )
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    parser.add_argument("--stage", default="dev", help="Environment stage")
    parser.add_argument("--bucket", help="Existing S3 bucket name (skip auto-detection)")
    args = parser.parse_args()

    print("=" * 60)
    print("Bedrock KB — Knowledge Base Setup")
    print("=" * 60)

    # Resolve AWS context
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    bucket = args.bucket or f"virtualassist-incident-kb-{account_id}-{args.region}"
    bucket_arn = f"arn:aws:s3:::{bucket}"

    role_name = f"bedrock-kb-incident-role-{args.stage}"
    collection_name = f"incident-kb-vectors-{args.stage}"
    kb_name = f"incident-management-kb-{args.stage}"

    print(f"\nAccount:    {account_id}")
    print(f"Region:     {args.region}")
    print(f"Stage:      {args.stage}")
    print(f"Bucket:     {bucket}")
    print(f"Collection: {collection_name}")
    print(f"KB Name:    {kb_name}")

    # Clients
    iam_client = boto3.client("iam")
    aoss_client = boto3.client("opensearchserverless", region_name=args.region)
    bedrock_client = boto3.client("bedrock-agent", region_name=args.region)

    # Step 1: IAM Role
    print("\nStep 1: IAM Role for Bedrock")
    role_arn = create_bedrock_role(iam_client, role_name, bucket_arn, account_id, args.region)
    print(f"  Role ARN: {role_arn}")

    # Step 2: AOSS Policies + Collection
    print("\nStep 2: OpenSearch Serverless Collection")
    create_aoss_policies(aoss_client, collection_name, role_arn, account_id)
    collection = create_aoss_collection(aoss_client, collection_name)
    print(f"  Collection ARN: {collection['arn']}")
    print(f"  Endpoint: {collection['endpoint']}")

    # Step 3: Vector Index
    print("\nStep 3: Vector Index")
    create_vector_index(collection["endpoint"], args.region)

    # Wait for index to propagate before KB creation
    print("  Waiting 30s for vector index propagation...")
    time.sleep(30)

    # Step 4: Knowledge Base (retry on index not found)
    print("\nStep 4: Knowledge Base")
    kb_id = None
    for attempt in range(3):
        try:
            kb_id = create_knowledge_base(
                bedrock_client, kb_name, role_arn, collection["arn"], args.region
            )
            break
        except Exception as e:
            if "no such index" in str(e) and attempt < 2:
                print(f"  Index not yet visible to Bedrock, retrying in 30s... (attempt {attempt + 2}/3)")
                time.sleep(30)
            else:
                raise

    if kb_id is None:
        print("  ERROR: Failed to create Knowledge Base after retries")
        sys.exit(1)

    # Output
    print("\n" + "=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print(f"\nKNOWLEDGE_BASE_ID = {kb_id}")
    print(f"COLLECTION_ENDPOINT = {collection['endpoint']}")
    print(f"ROLE_ARN = {role_arn}")
    print(f"\nNext step: Run ingest.py to create data source and index documents")
    print(f"  python ingest.py --kb-id {kb_id} --bucket {bucket}")

    return {
        "knowledge_base_id": kb_id,
        "collection_endpoint": collection["endpoint"],
        "role_arn": role_arn,
        "bucket": bucket,
    }


if __name__ == "__main__":
    main()
