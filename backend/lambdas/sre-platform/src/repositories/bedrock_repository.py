"""BedrockRepository — thin wrapper for bedrock-agent-runtime API.

Provides retrieve_and_generate() for AI-powered classification via
Bedrock Knowledge Base. Returns None on any failure for graceful degradation."""

import logging

import boto3
from botocore.exceptions import ClientError

from shared.middleware.observability import observe

logger = logging.getLogger(__name__)


class BedrockRepository:
    """Bedrock Agent Runtime wrapper. All methods return None on failure."""

    def __init__(self, bedrock_agent_client=None):
        self._client = bedrock_agent_client or boto3.client("bedrock-agent-runtime")

    @observe(operation="bedrock_retrieve_and_generate")
    def retrieve_and_generate(
        self,
        query: str,
        knowledge_base_id: str,
        model_arn: str,
        max_results: int = 5,
    ) -> dict | None:
        """Query the Knowledge Base with RetrieveAndGenerate API.

        Args:
            query: Natural language query with error context.
            knowledge_base_id: Bedrock KB ID.
            model_arn: Foundation model ARN for generation.
            max_results: Max retrieved chunks.

        Returns:
            API response dict or None on failure."""
        try:
            response = self._client.retrieve_and_generate(
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": knowledge_base_id,
                        "modelArn": model_arn,
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": max_results,
                            }
                        },
                    },
                },
            )
            return response
        except (ClientError, Exception) as exc:
            logger.warning("Bedrock RetrieveAndGenerate failed: %s", exc)
            return None
