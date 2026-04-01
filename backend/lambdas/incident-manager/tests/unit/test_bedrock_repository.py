"""Unit tests for BedrockRepository."""

import pytest
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError

from src.repositories.bedrock_repository import BedrockRepository


@pytest.fixture
def mock_bedrock_client():
    return Mock()


@pytest.fixture
def repo(mock_bedrock_client):
    return BedrockRepository(bedrock_agent_client=mock_bedrock_client)


class TestRetrieveAndGenerate:
    """Tests for retrieve_and_generate method."""

    def test_returns_response_on_success(self, repo, mock_bedrock_client):
        expected = {
            "output": {"text": '{"classification": "bad-deployment"}'},
            "citations": [],
        }
        mock_bedrock_client.retrieve_and_generate.return_value = expected

        result = repo.retrieve_and_generate(
            query="test query",
            knowledge_base_id="kb-123",
            model_arn="arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0",
        )

        assert result == expected
        mock_bedrock_client.retrieve_and_generate.assert_called_once()

    def test_passes_correct_api_structure(self, repo, mock_bedrock_client):
        mock_bedrock_client.retrieve_and_generate.return_value = {"output": {"text": ""}}

        repo.retrieve_and_generate(
            query="What are Lambda failure modes?",
            knowledge_base_id="kb-456",
            model_arn="arn:aws:bedrock:us-west-2::foundation-model/test-model",
            max_results=3,
        )

        call_kwargs = mock_bedrock_client.retrieve_and_generate.call_args[1]
        assert call_kwargs["input"]["text"] == "What are Lambda failure modes?"
        kb_config = call_kwargs["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]
        assert kb_config["knowledgeBaseId"] == "kb-456"
        assert kb_config["modelArn"] == "arn:aws:bedrock:us-west-2::foundation-model/test-model"
        assert kb_config["retrievalConfiguration"]["vectorSearchConfiguration"]["numberOfResults"] == 3

    def test_returns_none_on_client_error(self, repo, mock_bedrock_client):
        mock_bedrock_client.retrieve_and_generate.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "KB not found"}},
            "RetrieveAndGenerate",
        )

        result = repo.retrieve_and_generate(
            query="test", knowledge_base_id="bad-id", model_arn="bad-arn"
        )

        assert result is None

    def test_returns_none_on_generic_exception(self, repo, mock_bedrock_client):
        mock_bedrock_client.retrieve_and_generate.side_effect = RuntimeError("network error")

        result = repo.retrieve_and_generate(
            query="test", knowledge_base_id="kb-123", model_arn="arn"
        )

        assert result is None

    def test_default_max_results_is_five(self, repo, mock_bedrock_client):
        mock_bedrock_client.retrieve_and_generate.return_value = {"output": {"text": ""}}

        repo.retrieve_and_generate(query="test", knowledge_base_id="kb", model_arn="arn")

        call_kwargs = mock_bedrock_client.retrieve_and_generate.call_args[1]
        num_results = (
            call_kwargs["retrieveAndGenerateConfiguration"]
            ["knowledgeBaseConfiguration"]
            ["retrievalConfiguration"]
            ["vectorSearchConfiguration"]
            ["numberOfResults"]
        )
        assert num_results == 5
