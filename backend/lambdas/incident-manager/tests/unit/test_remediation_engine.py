"""Tests for RemediationEngine — skill-file-driven remediation dispatch."""

import pytest
from unittest.mock import Mock

from src.services.remediation.engine import RemediationEngine


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def engine():
    """RemediationEngine loaded with default skill files."""
    return RemediationEngine()


@pytest.fixture
def mock_config():
    """Mock config with nested remediation_catalog."""
    config = Mock()
    config.remediation_catalog = {
        "lambda": {
            "bad-deployment": {"action": "lambda-version-rollback"},
            "performance-degradation": {"action": "lambda-memory-increase"},
            "rate-limit": {"action": "increase-concurrency"},
        },
        "api-gateway": {
            "bad-deployment": {"action": "apigw-deployment-rollback"},
            "rate-limit": {"action": "apigw-throttle-increase"},
        },
        "elasticsearch": {
            "performance-degradation": {"action": "opensearch-scale-up"},
            "storage-exhaustion": {"action": "opensearch-storage-increase"},
        },
    }
    return config


@pytest.fixture
def mock_repo():
    """Mock RemediationRepository with all remediation methods."""
    repo = Mock()
    repo.rollback_lambda_version.return_value = {"status": "success"}
    repo.increase_lambda_memory.return_value = {"status": "success"}
    repo.increase_concurrency.return_value = {"status": "success"}
    repo.rollback_apigw_deployment.return_value = {"status": "success"}
    repo.update_apigw_throttle.return_value = {"status": "success"}
    repo.scale_opensearch_domain.return_value = {"status": "success"}
    repo.increase_opensearch_storage.return_value = {"status": "success"}
    return repo


# ------------------------------------------------------------------ #
# Skill File Loading
# ------------------------------------------------------------------ #

class TestSkillFileLoading:
    """Verify skill files are loaded correctly."""

    def test_loads_all_three_service_types(self, engine):
        types = engine.supported_service_types
        assert "lambda" in types
        assert "api-gateway" in types
        assert "elasticsearch" in types

    def test_loads_from_nonexistent_dir_gracefully(self):
        engine = RemediationEngine(skills_dir="/nonexistent/path")
        assert engine.supported_service_types == []


# ------------------------------------------------------------------ #
# Namespace Resolution
# ------------------------------------------------------------------ #

class TestResolveServiceType:
    """Verify namespace → service_type mapping from skill files."""

    def test_aws_lambda(self, engine):
        assert engine.resolve_service_type("AWS/Lambda") == "lambda"

    def test_custom_lambda(self, engine):
        assert engine.resolve_service_type("Custom/Lambda") == "lambda"

    def test_api_gateway(self, engine):
        assert engine.resolve_service_type("AWS/ApiGateway") == "api-gateway"

    def test_elasticsearch(self, engine):
        assert engine.resolve_service_type("AWS/ES") == "elasticsearch"

    def test_opensearch(self, engine):
        assert engine.resolve_service_type("AWS/OpenSearch") == "elasticsearch"

    def test_unknown_namespace(self, engine):
        assert engine.resolve_service_type("AWS/SQS") == "unknown"


# ------------------------------------------------------------------ #
# Resource Context Building
# ------------------------------------------------------------------ #

class TestBuildResourceContext:
    """Verify trigger dimensions are mapped to resource context using skill resource_keys."""

    def test_lambda_extracts_function_name(self, engine):
        ctx = engine.build_resource_context("lambda", {"FunctionName": "calc-api-prod"})
        assert ctx == {"function_name": "calc-api-prod"}

    def test_api_gateway_extracts_api_and_stage(self, engine):
        ctx = engine.build_resource_context("api-gateway", {"ApiId": "abc123", "Stage": "prod"})
        assert ctx == {"rest_api_id": "abc123", "stage_name": "prod"}

    def test_elasticsearch_extracts_domain(self, engine):
        ctx = engine.build_resource_context("elasticsearch", {"DomainName": "search-prod"})
        assert ctx == {"domain_name": "search-prod"}

    def test_unknown_service_type_returns_empty(self, engine):
        ctx = engine.build_resource_context("unknown", {"FunctionName": "test"})
        assert ctx == {}

    def test_missing_dimension_returns_empty_string(self, engine):
        ctx = engine.build_resource_context("lambda", {})
        assert ctx == {"function_name": ""}


# ------------------------------------------------------------------ #
# Remediation Dispatch — Lambda
# ------------------------------------------------------------------ #

class TestLambdaRemediation:
    """Verify Lambda skill file actions dispatch correctly."""

    def test_bad_deployment_calls_rollback(self, engine, mock_repo, mock_config):
        result = engine.attempt("lambda", "bad-deployment", {"function_name": "calc"}, mock_repo, mock_config)
        assert result is True
        mock_repo.rollback_lambda_version.assert_called_once_with(function_name="calc")

    def test_performance_degradation_calls_memory_increase(self, engine, mock_repo, mock_config):
        result = engine.attempt("lambda", "performance-degradation", {"function_name": "calc"}, mock_repo, mock_config)
        assert result is True
        mock_repo.increase_lambda_memory.assert_called_once_with(function_name="calc")

    def test_rate_limit_calls_increase_concurrency(self, engine, mock_repo, mock_config):
        result = engine.attempt("lambda", "rate-limit", {"function_name": "calc"}, mock_repo, mock_config)
        assert result is True
        mock_repo.increase_concurrency.assert_called_once_with(function_name="calc")

    def test_failure_returns_false(self, engine, mock_repo, mock_config):
        mock_repo.rollback_lambda_version.return_value = {"status": "failed"}
        result = engine.attempt("lambda", "bad-deployment", {"function_name": "calc"}, mock_repo, mock_config)
        assert result is False


# ------------------------------------------------------------------ #
# Remediation Dispatch — API Gateway
# ------------------------------------------------------------------ #

class TestApiGatewayRemediation:
    """Verify API Gateway skill file actions dispatch correctly."""

    def test_bad_deployment_calls_rollback(self, engine, mock_repo, mock_config):
        ctx = {"rest_api_id": "abc123", "stage_name": "prod"}
        result = engine.attempt("api-gateway", "bad-deployment", ctx, mock_repo, mock_config)
        assert result is True
        mock_repo.rollback_apigw_deployment.assert_called_once_with(rest_api_id="abc123", stage_name="prod")

    def test_rate_limit_calls_throttle_increase(self, engine, mock_repo, mock_config):
        ctx = {"rest_api_id": "abc123", "stage_name": "prod"}
        result = engine.attempt("api-gateway", "rate-limit", ctx, mock_repo, mock_config)
        assert result is True
        mock_repo.update_apigw_throttle.assert_called_once_with(rest_api_id="abc123", stage_name="prod")


# ------------------------------------------------------------------ #
# Remediation Dispatch — Elasticsearch
# ------------------------------------------------------------------ #

class TestElasticsearchRemediation:
    """Verify Elasticsearch skill file actions dispatch correctly."""

    def test_performance_degradation_calls_scale_up(self, engine, mock_repo, mock_config):
        ctx = {"domain_name": "search-prod"}
        result = engine.attempt("elasticsearch", "performance-degradation", ctx, mock_repo, mock_config)
        assert result is True
        mock_repo.scale_opensearch_domain.assert_called_once_with(domain_name="search-prod")

    def test_storage_exhaustion_calls_storage_increase(self, engine, mock_repo, mock_config):
        ctx = {"domain_name": "search-prod"}
        result = engine.attempt("elasticsearch", "storage-exhaustion", ctx, mock_repo, mock_config)
        assert result is True
        mock_repo.increase_opensearch_storage.assert_called_once_with(domain_name="search-prod")


# ------------------------------------------------------------------ #
# Edge Cases
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
# AI-Recommended Action
# ------------------------------------------------------------------ #

class TestAiRecommendedAction:
    """Verify ai_recommended_action overrides catalog when valid, falls back otherwise."""

    def test_known_action_overrides_catalog(self, engine, mock_repo, mock_config):
        """AI recommends a valid action that differs from catalog — AI wins."""
        mock_repo.increase_concurrency.return_value = {"status": "success"}
        result = engine.attempt(
            "lambda", "bad-deployment", {"function_name": "calc"}, mock_repo, mock_config,
            ai_recommended_action="increase-concurrency",
        )
        assert result is True
        mock_repo.increase_concurrency.assert_called_once_with(function_name="calc")
        mock_repo.rollback_lambda_version.assert_not_called()

    def test_unknown_action_falls_back_to_catalog(self, engine, mock_repo, mock_config):
        """AI recommends an action not in skill file — falls back to catalog."""
        result = engine.attempt(
            "lambda", "bad-deployment", {"function_name": "calc"}, mock_repo, mock_config,
            ai_recommended_action="nonexistent-action",
        )
        assert result is True
        mock_repo.rollback_lambda_version.assert_called_once_with(function_name="calc")

    def test_none_action_uses_catalog(self, engine, mock_repo, mock_config):
        """No AI recommendation — standard catalog lookup."""
        result = engine.attempt(
            "lambda", "bad-deployment", {"function_name": "calc"}, mock_repo, mock_config,
            ai_recommended_action=None,
        )
        assert result is True
        mock_repo.rollback_lambda_version.assert_called_once_with(function_name="calc")

    def test_ai_action_failure_does_not_cascade_to_catalog(self, engine, mock_repo, mock_config):
        """AI action found but fails — returns False, does NOT try catalog."""
        mock_repo.increase_concurrency.return_value = {"status": "failed"}
        result = engine.attempt(
            "lambda", "bad-deployment", {"function_name": "calc"}, mock_repo, mock_config,
            ai_recommended_action="increase-concurrency",
        )
        assert result is False
        mock_repo.rollback_lambda_version.assert_not_called()


# ------------------------------------------------------------------ #
# Edge Cases
# ------------------------------------------------------------------ #

class TestRemediationEdgeCases:
    """Verify graceful handling of missing/unknown entries."""

    def test_unknown_service_type_returns_none(self, engine, mock_repo, mock_config):
        result = engine.attempt("unknown", "bad-deployment", {}, mock_repo, mock_config)
        assert result is None

    def test_root_cause_not_in_catalog_returns_none(self, engine, mock_repo, mock_config):
        result = engine.attempt("lambda", "nonexistent-cause", {"function_name": "calc"}, mock_repo, mock_config)
        assert result is None

    def test_action_not_in_skill_returns_none(self, engine, mock_repo, mock_config):
        """If catalog references an action that the skill file doesn't define."""
        mock_config.remediation_catalog = {"lambda": {"test": {"action": "nonexistent-action"}}}
        result = engine.attempt("lambda", "test", {"function_name": "calc"}, mock_repo, mock_config)
        assert result is None

    def test_repo_method_not_found_returns_none(self, engine, mock_repo, mock_config):
        """If skill references a method that doesn't exist on the repo."""
        del mock_repo.rollback_lambda_version
        result = engine.attempt("lambda", "bad-deployment", {"function_name": "calc"}, mock_repo, mock_config)
        assert result is None
