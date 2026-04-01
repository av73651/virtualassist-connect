"""RemediationEngine — skill-file-driven remediation dispatch.

Loads JSON skill files at init. Each skill file describes a service type's
available remediation actions, the integration method to call, and what
parameters to extract from the resource context.

Adding a new service type = adding a skill JSON + repo methods. Zero engine changes."""

import json
import logging
from pathlib import Path

from shared.middleware.observability import observe

logger = logging.getLogger(__name__)

_DEFAULT_SKILLS_DIR = str(Path(__file__).parent / "skills")


class RemediationEngine:
    """Generic remediation engine driven by skill files.

    Skill files are JSON knowledge bases in the skills/ directory.
    Each describes: service_type, namespace_patterns, resource_keys, actions."""

    def __init__(self, skills_dir: str | None = None):
        self._skills: dict[str, dict] = {}
        self._namespace_map: dict[str, str] = {}
        self._load_skills(skills_dir or _DEFAULT_SKILLS_DIR)

    def _load_skills(self, skills_dir: str) -> None:
        """Load all .json skill files from the skills directory."""
        skills_path = Path(skills_dir)
        if not skills_path.is_dir():
            return

        for skill_file in skills_path.glob("*.json"):
            with open(skill_file) as f:
                skill = json.load(f)

            service_type = skill["service_type"]
            self._skills[service_type] = skill

            for namespace in skill.get("namespace_patterns", []):
                self._namespace_map[namespace] = service_type

    def resolve_service_type(self, namespace: str) -> str:
        """Resolve CloudWatch metric namespace to service_type.

        Returns 'unknown' if no skill file matches the namespace."""
        return self._namespace_map.get(namespace, "unknown")

    def build_resource_context(self, service_type: str, trigger_dimensions: dict[str, str]) -> dict:
        """Build resource context dict from trigger dimensions using skill resource_keys.

        Maps skill-defined resource key names to their values from trigger dimensions.
        E.g., skill says {"function_name": "FunctionName"} and dimensions has
        {"FunctionName": "calc-api-prod"} → {"function_name": "calc-api-prod"}."""
        skill = self._skills.get(service_type)
        if not skill:
            return {}

        resource_keys = skill.get("resource_keys", {})
        return {
            context_key: trigger_dimensions.get(dimension_name, "")
            for context_key, dimension_name in resource_keys.items()
        }

    @observe(operation="attempt_remediation", metric_prefix="remediation_engine")
    def attempt(
        self,
        service_type: str,
        root_cause: str,
        resource_context: dict,
        remediation_repo,
        config,
        ai_recommended_action: str | None = None,
    ) -> bool | None:
        """Attempt remediation using skill file knowledge.

        If ai_recommended_action is provided and maps to a valid skill action,
        it is tried first. Otherwise falls back to the catalog lookup.

        Returns True if remediation succeeded, False if it failed,
        None if no remediation is available for this service_type + root_cause."""
        skill = self._skills.get(service_type)
        if not skill:
            return None

        # Try AI-recommended action first (if valid in skill file)
        if ai_recommended_action:
            result = self._try_action(skill, ai_recommended_action, resource_context, remediation_repo)
            if result is not None:
                return result

        # Fall back to catalog lookup
        catalog = config.remediation_catalog.get(service_type, {})
        entry = catalog.get(root_cause)
        if not entry:
            return None

        return self._try_action(skill, entry["action"], resource_context, remediation_repo)

    def _try_action(
        self, skill: dict, action_name: str, resource_context: dict, remediation_repo,
    ) -> bool | None:
        """Try executing a specific action from the skill file.

        Returns True/False on success/failure, None if action is not valid."""
        action_def = skill["actions"].get(action_name)
        if not action_def:
            return None

        method = getattr(remediation_repo, action_def["method"], None)
        if not method:
            return None

        params = {
            key: resource_context.get(key, "")
            for key in action_def["params_from_context"]
        }

        result = method(**params)
        return result.get("status") == "success"

    @property
    def supported_service_types(self) -> list[str]:
        """Returns list of service types with loaded skill files."""
        return list(self._skills.keys())
