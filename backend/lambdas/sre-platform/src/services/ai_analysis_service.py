"""AIAnalysisService — single facade for all AI/KB interactions.

Owns: prompt templates, response parsing, KB communication.
Services call structured methods, get domain results back.
To switch AI provider, replace this one class — zero changes to services.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import json
import logging
import os
import re
from pathlib import Path

from shared.middleware.observability import observe

from src.domain.jira_formatting import group_error_patterns
from src.models.config import IncidentConfig
from src.models.enums import ResolutionOutcome
from src.repositories.bedrock_repository import BedrockRepository

logger = logging.getLogger(__name__)

_PROMPTS_DIR = str(Path(__file__).parent.parent / "prompts")

_VALID_CONFIDENCES = {"high", "medium", "low"}


def create_ai_service(config: IncidentConfig) -> "AIAnalysisService | None":
    """Factory: create AIAnalysisService if Bedrock KB is configured, else None.

    Resolves kb_id and model_arn from environment variables first,
    falling back to config values. Returns None when either is missing."""
    kb_id = os.environ.get("BEDROCK_KNOWLEDGE_BASE_ID", "") or config.bedrock_knowledge_base_id
    model_arn = os.environ.get("BEDROCK_MODEL_ARN", "") or config.bedrock_model_arn
    if not kb_id or not model_arn:
        return None
    bedrock_repo = BedrockRepository()
    return AIAnalysisService(bedrock_repo, kb_id, model_arn, config)


class AIAnalysisService:
    """Single facade for all AI/KB interactions.

    Consolidates IncidentClassifier and EscalationService._analyze_logs_with_bedrock()
    into one class. Services call structured methods, get domain results.
    Swap this class to change AI provider."""

    def __init__(
        self,
        bedrock_repository: BedrockRepository,
        knowledge_base_id: str,
        model_arn: str,
        config: IncidentConfig,
    ):
        self._repo = bedrock_repository
        self._kb_id = knowledge_base_id
        self._model_arn = model_arn
        self._valid_classifications = self._derive_classifications(config)
        self._classification_prompt = self._load_prompt("classification_prompt.txt")
        self._escalation_prompt = self._load_prompt("escalation_analysis_prompt.txt")
        self._resolution_prompt = self._load_prompt("resolution_summary_prompt.txt")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @observe(operation="classify_incident", metric_prefix="ai_analysis")
    def classify_incident(
        self,
        error_data: dict,
        service_type: str = "lambda",
        alarm_type: str = "",
        resource_identifier: str = "",
        stage: str = "",
        service_context: str = "",
        metric_name: str = "",
    ) -> dict | None:
        """Classify root cause and return combined AI analysis.

        Returns dict with classification, confidence, recommended_action,
        automation_level, reasoning, log_analysis, blast_radius,
        verification_guidance — or None if KB returns no response."""
        query = self._build_classification_query(
            error_data, service_type, alarm_type, resource_identifier, stage,
            service_context=service_context,
            metric_name=metric_name,
        )

        response = self._query_kb(query)
        if response is None:
            return None

        result = self._parse_classification_response(response)
        if result is not None:
            result["references"] = self._extract_references(response)
        return result

    @observe(operation="analyze_for_escalation", metric_prefix="ai_analysis")
    def analyze_for_escalation(
        self,
        error_logs: list[dict],
        service: str,
        stage: str,
        function_name: str,
        service_type: str = "lambda",
        alarm_type: str = "",
        reason: str = "",
        root_cause: str = "",
        confidence: str = "",
        remediation_outcome: str = "",
        verification: dict | None = None,
        log_analysis: str = "",
    ) -> dict | None:
        """Analyze incident for escalation.

        Returns dict with 'text' (analysis) and 'references' (KB sources), or None."""
        patterns, samples = group_error_patterns(
            error_logs, truncate_length=200, max_samples=3,
        )
        pattern_summary = self._format_top_patterns(patterns, fmt="count_prefix")

        remediation_summary = self._build_remediation_summary(
            remediation_outcome, reason, root_cause, verification,
        )

        query = self._escalation_prompt.format(
            function_name=function_name,
            service=service,
            stage=stage or "unknown",
            service_type=service_type or "lambda",
            alarm_type=alarm_type or "unknown",
            reason=reason,
            root_cause=root_cause or "unknown",
            confidence=confidence or "unknown",
            log_analysis=log_analysis or "No prior AI analysis available.",
            remediation_summary=remediation_summary,
            error_count=len(error_logs),
            pattern_summary=pattern_summary,
            sample_errors="\n".join(f"  - {s}" for s in samples),
        )

        response = self._query_kb(query)
        if response and "output" in response:
            return {
                "text": response["output"]["text"],
                "references": self._extract_references(response),
            }
        return None

    @observe(operation="generate_resolution_summary", metric_prefix="ai_analysis")
    def generate_resolution_summary(
        self,
        service: str,
        stage: str,
        service_type: str,
        root_cause: str,
        confidence: str,
        remediation_action: str,
        recovery_model: str,
        alarm_type: str,
        error_data: dict,
        log_analysis: str = "",
    ) -> dict | None:
        """Generate post-resolution AI summary.

        Returns dict with 'text' (summary) and 'references' (KB sources), or None."""
        patterns = error_data.get("error_patterns", {})
        pattern_summary = self._format_top_patterns(patterns, fmt="count_prefix", truncate=80) or "  (no patterns)"

        query = self._resolution_prompt.format(
            service=service,
            stage=stage,
            service_type=service_type,
            root_cause=root_cause,
            confidence=confidence,
            remediation_action=remediation_action,
            recovery_model=recovery_model,
            alarm_type=alarm_type,
            error_count=error_data.get("error_count", 0),
            pattern_summary=pattern_summary,
            log_analysis=log_analysis or "No prior AI analysis available.",
        )

        response = self._query_kb(query)
        if response and "output" in response:
            return {
                "text": response["output"]["text"],
                "references": self._extract_references(response),
            }
        return None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _query_kb(self, query: str) -> dict | None:
        """Send query to Knowledge Base. Returns response dict or None."""
        return self._repo.retrieve_and_generate(
            query=query,
            knowledge_base_id=self._kb_id,
            model_arn=self._model_arn,
        )

    @staticmethod
    def _extract_references(response: dict) -> list[dict]:
        """Extract KB source references from Bedrock citations.

        Deduplicates by source URI. Each reference contains:
        - source: S3 URI or location identifier of the runbook/document
        - content: retrieved text chunk used for generation"""
        seen_sources = set()
        references = []

        for citation in response.get("citations", []):
            for ref in citation.get("retrievedReferences", []):
                location = ref.get("location", {})
                loc_type = location.get("type", "")

                if loc_type == "S3":
                    source = location.get("s3Location", {}).get("uri", "")
                else:
                    source = location.get(f"{loc_type.lower()}Location", {}).get("uri", "") if loc_type else ""

                if not source or source in seen_sources:
                    continue

                seen_sources.add(source)
                content = ref.get("content", {}).get("text", "")
                references.append({
                    "source": source,
                    "content": content[:500] if content else "",
                })

        return references

    def _build_classification_query(
        self,
        error_data: dict,
        service_type: str,
        alarm_type: str,
        resource_identifier: str,
        stage: str,
        service_context: str = "",
        metric_name: str = "",
    ) -> str:
        """Build structured query from error data for classification."""
        patterns = error_data.get("error_patterns", {})
        top_patterns_str = self._format_top_patterns(patterns, fmt="count_suffix") or "  (no patterns detected)"

        samples = error_data.get("sample_payloads", [])
        sample_str = "\n".join(
            f"  - {msg[:200]}" for msg in samples[:3]
        ) or "  (no samples available)"

        valid_str = ", ".join(sorted(self._valid_classifications))

        return self._classification_prompt.format(
            service_type=service_type,
            alarm_type=alarm_type or "unknown",
            resource_identifier=resource_identifier or "unknown",
            stage=stage or "unknown",
            error_count=error_data.get("error_count", 0),
            unique_errors=error_data.get("unique_errors", 0),
            top_patterns=top_patterns_str,
            sample_messages=sample_str,
            valid_classifications=valid_str,
            service_context=service_context or "(no service architecture metadata available)",
            metric_name=metric_name or "unknown",
        )

    def _parse_classification_response(self, response: dict) -> dict | None:
        """Extract JSON classification from KB response.

        Returns None for empty response text or invalid classification.
        Raises json.JSONDecodeError on malformed JSON — @observe handles logging."""
        output = response.get("output", {}).get("text", "")
        if not output:
            return None

        parsed = self._extract_json(output)

        classification = parsed.get("classification", "")
        if classification not in self._valid_classifications:
            return None

        confidence = parsed.get("confidence", "low")
        if confidence not in _VALID_CONFIDENCES:
            confidence = "low"

        return {
            "classification": classification,
            "confidence": confidence,
            "recommended_action": parsed.get("recommended_action", ""),
            "automation_level": parsed.get("automation_level", "manual"),
            "reasoning": parsed.get("reasoning", ""),
            "log_analysis": parsed.get("log_analysis", ""),
            "blast_radius": parsed.get("blast_radius", ""),
            "verification_guidance": parsed.get("verification_guidance", ""),
        }

    @staticmethod
    def _format_top_patterns(
        patterns: dict, fmt: str = "count_prefix", truncate: int = 0, limit: int = 5,
    ) -> str:
        """Format top error patterns as a multi-line string.

        fmt='count_prefix': '  [5x] ImportError'
        fmt='count_suffix': '  - ImportError (count: 5)'"""
        top = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:limit]
        if fmt == "count_suffix":
            return "\n".join(
                f"  - {pat[:truncate] if truncate else pat} (count: {cnt})"
                for pat, cnt in top
            )
        return "\n".join(
            f"  [{cnt}x] {pat[:truncate] if truncate else pat}"
            for pat, cnt in top
        )

    @staticmethod
    def _build_remediation_summary(
        outcome: str, reason: str, root_cause: str, verification: dict | None,
    ) -> str:
        """Build human-readable remediation summary from outcome."""
        if outcome == "not-attempted":
            return f"No remediation attempted (reason: {reason})"
        if outcome == ResolutionOutcome.NO_REMEDIATION:
            return f"No automated remediation available for root cause '{root_cause}'"
        if outcome == ResolutionOutcome.REMEDIATION_FAILED:
            return "Auto-remediation attempted but the action failed"
        if outcome == ResolutionOutcome.VERIFICATION_FAILED and verification:
            return (
                f"Auto-remediation completed but verification failed: "
                f"alarm_ok={verification.get('alarm_ok')}, "
                f"health_ok={verification.get('health_ok')}, "
                f"error_rate_ok={verification.get('error_rate_ok')}"
            )
        return f"Escalation reason: {reason}"

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON object from LLM response text.

        Handles code-fenced and bare JSON. Raises json.JSONDecodeError on failure."""
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])

        raise json.JSONDecodeError("No JSON object found in response", text, 0)

    @staticmethod
    def _derive_classifications(config: IncidentConfig) -> set[str]:
        """Derive valid classifications from remediation_catalog keys + 'unknown'."""
        classifications = {"unknown"}
        for service_type_catalog in config.remediation_catalog.values():
            classifications.update(service_type_catalog.keys())
        return classifications

    @staticmethod
    def _load_prompt(filename: str) -> str:
        """Load prompt template from prompts directory."""
        with open(f"{_PROMPTS_DIR}/{filename}") as f:
            return f.read()
