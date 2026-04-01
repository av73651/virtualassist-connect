"""Unit tests for AIAnalysisService — single AI facade for all KB interactions."""

import json
import pytest
from unittest.mock import Mock

from src.services.ai_analysis_service import AIAnalysisService


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_bedrock_repo():
    return Mock()


@pytest.fixture
def ai_service(mock_bedrock_repo, incident_config):
    return AIAnalysisService(
        bedrock_repository=mock_bedrock_repo,
        knowledge_base_id="kb-test-123",
        model_arn="arn:aws:bedrock:us-west-2::foundation-model/test",
        config=incident_config,
    )


@pytest.fixture
def import_error_data():
    return {
        "error_patterns": {"ImportError: No module named 'foo'": 50},
        "error_count": 50,
        "unique_errors": 1,
        "sample_payloads": [
            "ImportError: No module named 'foo'",
            "ImportError: No module named 'foo'",
        ],
    }


@pytest.fixture
def throttle_error_data():
    return {
        "error_patterns": {"TooManyRequestsException: Rate exceeded": 30},
        "error_count": 30,
        "unique_errors": 1,
        "sample_payloads": ["TooManyRequestsException: Rate exceeded"],
    }


_MOCK_CITATIONS = [
    {
        "generatedResponsePart": {"textResponsePart": {"text": "snippet", "span": {"start": 0, "end": 10}}},
        "retrievedReferences": [
            {
                "content": {"text": "Lambda error handling guidance from runbook"},
                "location": {"type": "S3", "s3Location": {"uri": "s3://kb-bucket/incident-management-lambda.md"}},
            },
        ],
    },
]


def _bedrock_response(classification_json: dict, citations: list | None = None) -> dict:
    """Build a mock Bedrock RetrieveAndGenerate response."""
    return {
        "output": {"text": json.dumps(classification_json)},
        "citations": citations if citations is not None else _MOCK_CITATIONS,
    }


# ------------------------------------------------------------------ #
# Valid classifications derived from config
# ------------------------------------------------------------------ #

class TestValidClassifications:
    """Verify classifications are derived from config.remediation_catalog."""

    def test_includes_catalog_root_causes(self, ai_service):
        assert "bad-deployment" in ai_service._valid_classifications
        assert "performance-degradation" in ai_service._valid_classifications
        assert "rate-limit" in ai_service._valid_classifications
        assert "storage-exhaustion" in ai_service._valid_classifications

    def test_includes_unknown_fallback(self, ai_service):
        assert "unknown" in ai_service._valid_classifications

    def test_does_not_include_arbitrary_values(self, ai_service):
        assert "not-a-real-thing" not in ai_service._valid_classifications


# ------------------------------------------------------------------ #
# classify_incident tests
# ------------------------------------------------------------------ #

class TestClassifyIncident:
    """Tests for AIAnalysisService.classify_incident()."""

    def test_happy_path_returns_all_fields(self, ai_service, mock_bedrock_repo, import_error_data):
        mock_bedrock_repo.retrieve_and_generate.return_value = _bedrock_response({
            "classification": "bad-deployment",
            "confidence": "high",
            "recommended_action": "lambda-version-rollback",
            "automation_level": "auto",
            "reasoning": "ImportError indicates a bad deployment with missing module",
            "log_analysis": "The error pattern shows ImportError across all invocations",
            "blast_radius": "Total outage — 100% of requests failing",
            "verification_guidance": "Error rate should drop to 0%, alarm returns to OK",
        })

        result = ai_service.classify_incident(import_error_data, service_type="lambda", alarm_type="error-rate")

        assert result is not None
        assert result["classification"] == "bad-deployment"
        assert result["confidence"] == "high"
        assert result["recommended_action"] == "lambda-version-rollback"
        assert result["automation_level"] == "auto"
        assert "ImportError" in result["reasoning"]
        assert result["log_analysis"] != ""
        assert result["blast_radius"] != ""
        assert result["verification_guidance"] != ""
        assert len(result["references"]) == 1
        assert "incident-management-lambda.md" in result["references"][0]["source"]

    def test_throttle_classification(self, ai_service, mock_bedrock_repo, throttle_error_data):
        mock_bedrock_repo.retrieve_and_generate.return_value = _bedrock_response({
            "classification": "rate-limit",
            "confidence": "high",
            "recommended_action": "increase-concurrency",
            "automation_level": "auto",
            "reasoning": "TooManyRequestsException indicates rate limiting",
            "log_analysis": "Throttling pattern detected",
            "blast_radius": "Partial degradation — some requests rejected",
            "verification_guidance": "Throttle count drops to 0",
        })

        result = ai_service.classify_incident(throttle_error_data, service_type="lambda")

        assert result["classification"] == "rate-limit"
        assert result["confidence"] == "high"

    def test_returns_none_when_repo_returns_none(self, ai_service, mock_bedrock_repo, import_error_data):
        mock_bedrock_repo.retrieve_and_generate.return_value = None

        result = ai_service.classify_incident(import_error_data)

        assert result is None

    def test_returns_none_on_empty_response_text(self, ai_service, mock_bedrock_repo, import_error_data):
        mock_bedrock_repo.retrieve_and_generate.return_value = {"output": {"text": ""}}

        result = ai_service.classify_incident(import_error_data)

        assert result is None

    def test_returns_none_on_invalid_classification(self, ai_service, mock_bedrock_repo, import_error_data):
        mock_bedrock_repo.retrieve_and_generate.return_value = _bedrock_response({
            "classification": "not-a-valid-classification",
            "confidence": "high",
        })

        result = ai_service.classify_incident(import_error_data)

        assert result is None

    def test_parses_json_in_code_fences(self, ai_service, mock_bedrock_repo, import_error_data):
        fenced = '```json\n{"classification": "bad-deployment", "confidence": "high", "recommended_action": "rollback", "automation_level": "auto", "reasoning": "test", "log_analysis": "", "blast_radius": "", "verification_guidance": ""}\n```'
        mock_bedrock_repo.retrieve_and_generate.return_value = {"output": {"text": fenced}, "citations": []}

        result = ai_service.classify_incident(import_error_data)

        assert result is not None
        assert result["classification"] == "bad-deployment"
        assert result["references"] == []

    def test_raises_on_malformed_json(self, ai_service, mock_bedrock_repo, import_error_data):
        mock_bedrock_repo.retrieve_and_generate.return_value = {
            "output": {"text": "This is not JSON at all"}
        }

        with pytest.raises(json.JSONDecodeError):
            ai_service.classify_incident(import_error_data)

    def test_normalizes_invalid_confidence_to_low(self, ai_service, mock_bedrock_repo, import_error_data):
        mock_bedrock_repo.retrieve_and_generate.return_value = _bedrock_response({
            "classification": "bad-deployment",
            "confidence": "very-high",
            "recommended_action": "rollback",
            "automation_level": "auto",
            "reasoning": "test",
        })

        result = ai_service.classify_incident(import_error_data)

        assert result["confidence"] == "low"

    def test_accepts_resource_identifier_and_stage(self, ai_service, mock_bedrock_repo, import_error_data):
        mock_bedrock_repo.retrieve_and_generate.return_value = _bedrock_response({
            "classification": "bad-deployment",
            "confidence": "high",
            "recommended_action": "rollback",
            "automation_level": "auto",
            "reasoning": "test",
        })

        result = ai_service.classify_incident(
            import_error_data,
            service_type="lambda",
            alarm_type="error-rate",
            resource_identifier="calculator-api-prod",
            stage="prod",
        )

        assert result is not None
        # Verify the query was built with resource and stage
        query = mock_bedrock_repo.retrieve_and_generate.call_args[1]["query"]
        assert "calculator-api-prod" in query
        assert "prod" in query


class TestBuildClassificationQuery:
    """Tests for query construction."""

    def test_query_contains_service_type(self, ai_service, import_error_data):
        query = ai_service._build_classification_query(import_error_data, "lambda", "error-rate", "", "")
        assert "lambda" in query
        assert "error-rate" in query

    def test_query_contains_error_patterns(self, ai_service, import_error_data):
        query = ai_service._build_classification_query(import_error_data, "lambda", "", "", "")
        assert "ImportError" in query
        assert "50" in query

    def test_query_contains_valid_classifications(self, ai_service, import_error_data):
        query = ai_service._build_classification_query(import_error_data, "lambda", "", "", "")
        assert "bad-deployment" in query
        assert "rate-limit" in query

    def test_empty_error_data_still_builds_query(self, ai_service):
        query = ai_service._build_classification_query(
            {"error_patterns": {}, "error_count": 0, "unique_errors": 0, "sample_payloads": []},
            "lambda", "", "", "",
        )
        assert "Error count: 0" in query
        assert "no patterns detected" in query

    def test_query_loaded_from_prompt_file(self, ai_service, import_error_data):
        query = ai_service._build_classification_query(import_error_data, "lambda", "error-rate", "", "")
        assert "automated incident response system" in query
        assert "Required Output" in query

    def test_query_includes_resource_and_stage(self, ai_service, import_error_data):
        query = ai_service._build_classification_query(
            import_error_data, "lambda", "error-rate", "calc-api-prod", "prod",
        )
        assert "calc-api-prod" in query
        assert "prod" in query


# ------------------------------------------------------------------ #
# analyze_for_escalation tests
# ------------------------------------------------------------------ #

class TestAnalyzeForEscalation:
    """Tests for AIAnalysisService.analyze_for_escalation()."""

    def test_returns_dict_on_success(self, ai_service, mock_bedrock_repo):
        mock_bedrock_repo.retrieve_and_generate.return_value = {
            "output": {"text": "Root cause analysis: ImportError indicates bad deployment."},
            "citations": _MOCK_CITATIONS,
        }

        result = ai_service.analyze_for_escalation(
            error_logs=[{"@message": "ImportError: No module named 'foo'"}],
            service="calculator",
            stage="prod",
            function_name="calculator-api-prod",
            reason="verification-failed",
            root_cause="bad-deployment",
        )

        assert result is not None
        assert "ImportError" in result["text"]
        assert len(result["references"]) == 1
        assert "incident-management-lambda.md" in result["references"][0]["source"]

    def test_returns_none_when_kb_returns_none(self, ai_service, mock_bedrock_repo):
        mock_bedrock_repo.retrieve_and_generate.return_value = None

        result = ai_service.analyze_for_escalation(
            error_logs=[{"@message": "error"}],
            service="test", stage="dev", function_name="test-fn",
        )

        assert result is None

    def test_query_includes_remediation_summary(self, ai_service, mock_bedrock_repo):
        mock_bedrock_repo.retrieve_and_generate.return_value = {"output": {"text": "analysis"}, "citations": []}

        ai_service.analyze_for_escalation(
            error_logs=[{"@message": "error"}],
            service="test", stage="dev", function_name="test-fn",
            remediation_outcome="verification-failed",
            verification={"alarm_ok": False, "health_ok": True, "error_rate_ok": True},
        )

        query = mock_bedrock_repo.retrieve_and_generate.call_args[1]["query"]
        assert "verification failed" in query
        assert "alarm_ok=False" in query


# ------------------------------------------------------------------ #
# generate_resolution_summary tests
# ------------------------------------------------------------------ #

class TestGenerateResolutionSummary:
    """Tests for AIAnalysisService.generate_resolution_summary()."""

    def test_returns_dict_on_success(self, ai_service, mock_bedrock_repo):
        mock_bedrock_repo.retrieve_and_generate.return_value = {
            "output": {"text": "The incident was caused by a bad deployment..."},
            "citations": _MOCK_CITATIONS,
        }

        result = ai_service.generate_resolution_summary(
            service="calculator", stage="prod", service_type="lambda",
            root_cause="bad-deployment", confidence="high",
            remediation_action="lambda-version-rollback",
            recovery_model="stateless", alarm_type="error-rate",
            error_data={"error_patterns": {"ImportError": 50}, "error_count": 50},
        )

        assert result is not None
        assert "bad deployment" in result["text"]
        assert len(result["references"]) == 1

    def test_returns_none_when_kb_returns_none(self, ai_service, mock_bedrock_repo):
        mock_bedrock_repo.retrieve_and_generate.return_value = None

        result = ai_service.generate_resolution_summary(
            service="test", stage="dev", service_type="lambda",
            root_cause="unknown", confidence="low",
            remediation_action="test", recovery_model="stateless",
            alarm_type="error-rate",
            error_data={"error_patterns": {}, "error_count": 0},
        )

        assert result is None


# ------------------------------------------------------------------ #
# _build_remediation_summary tests
# ------------------------------------------------------------------ #

class TestBuildRemediationSummary:
    """Tests for remediation summary formatting."""

    def test_not_attempted(self):
        result = AIAnalysisService._build_remediation_summary(
            "not-attempted", "incident-storm", "bad-deployment", None,
        )
        assert "No remediation attempted" in result

    def test_no_remediation(self):
        result = AIAnalysisService._build_remediation_summary(
            "no-remediation", "", "unknown", None,
        )
        assert "No automated remediation available" in result

    def test_remediation_failed(self):
        result = AIAnalysisService._build_remediation_summary(
            "remediation-failed", "", "bad-deployment", None,
        )
        assert "action failed" in result

    def test_verification_failed(self):
        result = AIAnalysisService._build_remediation_summary(
            "verification-failed", "", "bad-deployment",
            {"alarm_ok": False, "health_ok": True, "error_rate_ok": True},
        )
        assert "verification failed" in result
        assert "alarm_ok=False" in result

    def test_default_reason(self):
        result = AIAnalysisService._build_remediation_summary(
            "other", "custom-reason", "", None,
        )
        assert "custom-reason" in result


# ------------------------------------------------------------------ #
# _extract_json tests
# ------------------------------------------------------------------ #

class TestExtractJson:
    """Tests for JSON extraction from LLM responses."""

    def test_bare_json(self):
        result = AIAnalysisService._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_code_fenced_json(self):
        result = AIAnalysisService._extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_code_fenced_no_lang(self):
        result = AIAnalysisService._extract_json('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        result = AIAnalysisService._extract_json('Here is the result: {"key": "value"} end')
        assert result == {"key": "value"}

    def test_malformed_raises(self):
        with pytest.raises(json.JSONDecodeError):
            AIAnalysisService._extract_json("no json here")


# ------------------------------------------------------------------ #
# _extract_references tests
# ------------------------------------------------------------------ #

class TestExtractReferences:
    """Tests for KB citation extraction."""

    def test_extracts_s3_references(self):
        response = {
            "citations": [
                {
                    "generatedResponsePart": {"textResponsePart": {"text": "x"}},
                    "retrievedReferences": [
                        {
                            "content": {"text": "Lambda rollback procedure"},
                            "location": {"type": "S3", "s3Location": {"uri": "s3://kb/lambda.md"}},
                        },
                    ],
                },
            ],
        }
        refs = AIAnalysisService._extract_references(response)
        assert len(refs) == 1
        assert refs[0]["source"] == "s3://kb/lambda.md"
        assert "rollback" in refs[0]["content"]

    def test_deduplicates_same_source(self):
        response = {
            "citations": [
                {
                    "retrievedReferences": [
                        {"content": {"text": "chunk 1"}, "location": {"type": "S3", "s3Location": {"uri": "s3://kb/lambda.md"}}},
                    ],
                },
                {
                    "retrievedReferences": [
                        {"content": {"text": "chunk 2"}, "location": {"type": "S3", "s3Location": {"uri": "s3://kb/lambda.md"}}},
                    ],
                },
            ],
        }
        refs = AIAnalysisService._extract_references(response)
        assert len(refs) == 1

    def test_multiple_sources(self):
        response = {
            "citations": [
                {
                    "retrievedReferences": [
                        {"content": {"text": "a"}, "location": {"type": "S3", "s3Location": {"uri": "s3://kb/lambda.md"}}},
                        {"content": {"text": "b"}, "location": {"type": "S3", "s3Location": {"uri": "s3://kb/api-gateway.md"}}},
                    ],
                },
            ],
        }
        refs = AIAnalysisService._extract_references(response)
        assert len(refs) == 2
        sources = {r["source"] for r in refs}
        assert "s3://kb/lambda.md" in sources
        assert "s3://kb/api-gateway.md" in sources

    def test_empty_citations(self):
        refs = AIAnalysisService._extract_references({"citations": []})
        assert refs == []

    def test_missing_citations_key(self):
        refs = AIAnalysisService._extract_references({})
        assert refs == []

    def test_truncates_long_content(self):
        long_text = "x" * 1000
        response = {
            "citations": [
                {
                    "retrievedReferences": [
                        {"content": {"text": long_text}, "location": {"type": "S3", "s3Location": {"uri": "s3://kb/doc.md"}}},
                    ],
                },
            ],
        }
        refs = AIAnalysisService._extract_references(response)
        assert len(refs[0]["content"]) == 500


# ------------------------------------------------------------------ #
# TriageService AI fallback integration (moved from test_incident_classifier)
# ------------------------------------------------------------------ #

class TestTriageServiceAIFallback:
    """Tests for AI-first, rule-fallback classification in TriageService."""

    @staticmethod
    def _make_triage_service(incident_config, mock_correlation_repo, mock_event_bus_repo,
                             mock_log_analysis_service, mock_resolution_service,
                             mock_incident_reporter, ai_service=None):
        from src.services.triage_service import TriageService
        return TriageService(
            correlation_repo=mock_correlation_repo,
            event_bus_repo=mock_event_bus_repo,
            config=incident_config,
            log_analysis_service=mock_log_analysis_service,
            ai_service=ai_service,
            resolution_service=mock_resolution_service,
            incident_reporter=mock_incident_reporter,
        )

    def test_ai_result_used_when_available(self, incident_config, mock_correlation_repo, mock_event_bus_repo, mock_log_analysis_service, mock_resolution_service, mock_incident_reporter):
        mock_ai = Mock()
        mock_ai.classify_incident.return_value = {
            "classification": "bad-deployment",
            "confidence": "high",
            "recommended_action": "lambda-version-rollback",
            "automation_level": "auto",
            "reasoning": "AI detected ImportError pattern",
            "log_analysis": "ImportError indicates missing dependency",
            "blast_radius": "Total outage",
            "verification_guidance": "Error rate drops to 0%",
            "references": [{"source": "s3://kb/lambda.md", "content": "rollback procedure"}],
        }

        service = self._make_triage_service(
            incident_config, mock_correlation_repo, mock_event_bus_repo,
            mock_log_analysis_service, mock_resolution_service, mock_incident_reporter,
            ai_service=mock_ai,
        )

        error_data = {
            "error_patterns": {"ImportError": 10},
            "error_count": 10,
            "unique_errors": 1,
            "sample_payloads": ["ImportError: No module named 'foo'"],
        }

        result = service._classify_root_cause(error_data)

        assert result["root_cause"] == "bad-deployment"
        assert result["confidence"] == "high"
        assert "AI detected" in result["evidence"]
        mock_ai.classify_incident.assert_called_once()

    def test_falls_back_to_rules_when_ai_returns_none(self, incident_config, mock_correlation_repo, mock_event_bus_repo, mock_log_analysis_service, mock_resolution_service, mock_incident_reporter):
        mock_ai = Mock()
        mock_ai.classify_incident.return_value = None

        service = self._make_triage_service(
            incident_config, mock_correlation_repo, mock_event_bus_repo,
            mock_log_analysis_service, mock_resolution_service, mock_incident_reporter,
            ai_service=mock_ai,
        )

        error_data = {
            "error_patterns": {"ImportError: No module named 'foo'": 10},
            "error_count": 10,
            "unique_errors": 1,
            "sample_payloads": ["ImportError: No module named 'foo'"],
        }

        result = service._classify_root_cause(error_data)

        assert result["root_cause"] == "bad-deployment"
        assert result["confidence"] == "high"
        mock_ai.classify_incident.assert_called_once()

    def test_no_ai_service_uses_rules_only(self, incident_config, mock_correlation_repo, mock_event_bus_repo, mock_log_analysis_service, mock_resolution_service, mock_incident_reporter):
        service = self._make_triage_service(
            incident_config, mock_correlation_repo, mock_event_bus_repo,
            mock_log_analysis_service, mock_resolution_service, mock_incident_reporter,
            ai_service=None,
        )

        error_data = {
            "error_patterns": {"TooManyRequestsException: Rate exceeded": 15, "TimeoutError": 5},
            "error_count": 20,
            "unique_errors": 2,
            "sample_payloads": ["TooManyRequestsException: Rate exceeded", "TimeoutError"],
        }

        result = service._classify_root_cause(error_data)

        assert result["root_cause"] == "rate-limit"
