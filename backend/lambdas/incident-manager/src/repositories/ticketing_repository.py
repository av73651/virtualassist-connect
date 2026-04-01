"""TicketingRepository — Jira REST API v3 operations.

Handles ticket creation, comments, file attachments, and status transitions.
Credentials loaded from AWS Secrets Manager and cached after first call.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import json
import logging

import boto3
import requests

from shared.middleware.observability import observe

from src.models.config import IncidentConfig

logger = logging.getLogger(__name__)


class TicketingRepository:
    """Jira REST API v3 — ticket lifecycle operations."""

    def __init__(
        self,
        config: IncidentConfig,
        jira_url: str,
        jira_project_key: str = "ASD",
        jira_secret_name: str = "incident-manager/jira-credentials",
        secrets_client=None,
    ):
        self._config = config
        self._jira_url = jira_url.rstrip("/")
        self._jira_project_key = jira_project_key
        self._jira_secret_name = jira_secret_name
        self._secrets_client = secrets_client or boto3.client("secretsmanager")
        self._credentials: dict | None = None

    # ------------------------------------------------------------------ #
    # Credentials
    # ------------------------------------------------------------------ #

    def _get_credentials(self) -> dict:
        """Load Jira credentials from Secrets Manager. Cached after first call."""
        if self._credentials is not None:
            return self._credentials

        response = self._secrets_client.get_secret_value(
            SecretId=self._jira_secret_name
        )
        self._credentials = json.loads(response["SecretString"])
        return self._credentials

    def _auth(self) -> tuple[str, str]:
        """Returns (email, api_token) tuple for basic auth."""
        creds = self._get_credentials()
        return (creds["email"], creds["api_token"])

    def _reporter_account_id(self) -> str | None:
        """Returns Jira account_id for the service account reporter, or None."""
        return self._get_credentials().get("account_id")

    def _headers(self) -> dict:
        """Standard Jira API headers."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Ticket operations
    # ------------------------------------------------------------------ #

    @observe(operation="create_jira_ticket", metric_prefix="jira_create")
    def create_jira_ticket(
        self,
        summary: str,
        description: str,
        priority: str,
        labels: list[str],
        incident_key: str,
    ) -> str | None:
        """Creates Jira Service Management request. Returns ticket key or None on failure.

        Uses JSM Service Desk API to set request type ('Report a system problem').
        Falls back to standard Jira API if service desk config is missing."""
        try:
            service_desk_id = self._config.jira_service_desk_id
            request_type_id = self._config.jira_request_type_id

            if service_desk_id and request_type_id:
                return self._create_jsm_request(
                    summary, description, priority, labels, service_desk_id, request_type_id,
                )

            return self._create_jira_issue(summary, description, priority, labels)

        except Exception as exc:
            logger.warning("Jira ticket creation failed: %s", exc)
            return None

    def _create_jsm_request(
        self,
        summary: str,
        description: str,
        priority: str,
        labels: list[str],
        service_desk_id: str,
        request_type_id: str,
    ) -> str | None:
        """Creates ticket via JSM Service Desk API with proper request type.

        JSM request types only accept specific fields, so we create the request
        with summary/description, then set priority and labels via standard API."""
        payload = {
            "serviceDeskId": service_desk_id,
            "requestTypeId": request_type_id,
            "requestFieldValues": {
                "summary": summary,
                "description": description,
            },
        }

        response = requests.post(
            f"{self._jira_url}/rest/servicedeskapi/request",
            headers=self._headers(),
            auth=self._auth(),
            json=payload,
            timeout=self._config.jira_http_timeout_seconds,
        )
        response.raise_for_status()

        issue_key = response.json()["issueKey"]

        # Set priority and labels via standard Jira API (not supported in JSM request creation)
        priority_map = self._config.jira_priority_map
        update_fields = {
            "priority": {"name": priority_map.get(priority, "Medium")},
            "labels": labels,
        }
        try:
            requests.put(
                f"{self._jira_url}/rest/api/3/issue/{issue_key}",
                headers=self._headers(),
                auth=self._auth(),
                json={"fields": update_fields},
                timeout=self._config.jira_http_timeout_seconds,
            )
        except Exception:
            logger.warning("Failed to set priority/labels on %s", issue_key)

        return issue_key

    def _create_jira_issue(
        self,
        summary: str,
        description: str,
        priority: str,
        labels: list[str],
    ) -> str | None:
        """Fallback: creates ticket via standard Jira REST API v3."""
        priority_map = self._config.jira_priority_map
        fields = {
            "project": {"key": self._jira_project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            },
            "issuetype": {"name": self._config.jira_issue_type},
            "priority": {"name": priority_map.get(priority, "Medium")},
            "labels": labels,
        }

        reporter_id = self._reporter_account_id()
        if reporter_id:
            fields["reporter"] = {"accountId": reporter_id}

        response = requests.post(
            f"{self._jira_url}/rest/api/3/issue",
            headers=self._headers(),
            auth=self._auth(),
            json={"fields": fields},
            timeout=self._config.jira_http_timeout_seconds,
        )
        response.raise_for_status()

        return response.json()["key"]

    @observe(operation="add_jira_comment", metric_prefix="jira_comment")
    def add_jira_comment(self, ticket_key: str, comment: str) -> bool:
        """Adds plain text comment to Jira ticket. Returns False on failure."""
        try:
            payload = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": comment}],
                        }
                    ],
                }
            }

            response = requests.post(
                f"{self._jira_url}/rest/api/3/issue/{ticket_key}/comment",
                headers=self._headers(),
                auth=self._auth(),
                json=payload,
                timeout=self._config.jira_http_timeout_seconds,
            )
            response.raise_for_status()

            return True

        except Exception:
            return False

    @observe(operation="add_jira_comment_adf", metric_prefix="jira_comment_adf")
    def add_jira_comment_adf(self, ticket_key: str, adf_content: list[dict]) -> bool:
        """Adds rich ADF-formatted comment to Jira ticket. Returns False on failure."""
        try:
            payload = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": adf_content,
                }
            }

            response = requests.post(
                f"{self._jira_url}/rest/api/3/issue/{ticket_key}/comment",
                headers=self._headers(),
                auth=self._auth(),
                json=payload,
                timeout=self._config.jira_http_timeout_seconds,
            )
            response.raise_for_status()

            return True

        except Exception:
            return False

    @observe(operation="attach_jira_file", metric_prefix="jira_attach")
    def attach_jira_file(
        self, ticket_key: str, filename: str, content: str
    ) -> bool:
        """Attaches text file to Jira ticket. Returns False on failure."""
        try:
            headers = {"X-Atlassian-Token": "no-check"}

            response = requests.post(
                f"{self._jira_url}/rest/api/3/issue/{ticket_key}/attachments",
                headers=headers,
                auth=self._auth(),
                files={"file": (filename, content, "text/plain")},
                timeout=self._config.jira_http_timeout_seconds,
            )
            response.raise_for_status()

            return True

        except Exception:
            return False

    @observe(operation="transition_jira_ticket", metric_prefix="jira_transition")
    def transition_jira_ticket(self, ticket_key: str, transition_name: str) -> bool:
        """Transitions Jira ticket status. Returns False on failure."""
        try:
            response = requests.get(
                f"{self._jira_url}/rest/api/3/issue/{ticket_key}/transitions",
                headers=self._headers(),
                auth=self._auth(),
                timeout=self._config.jira_http_timeout_seconds,
            )
            response.raise_for_status()

            transitions = response.json().get("transitions", [])
            target = None
            for t in transitions:
                if t["name"].lower() == transition_name.lower():
                    target = t
                    break

            if not target:
                return False

            response = requests.post(
                f"{self._jira_url}/rest/api/3/issue/{ticket_key}/transitions",
                headers=self._headers(),
                auth=self._auth(),
                json={"transition": {"id": target["id"]}},
                timeout=self._config.jira_http_timeout_seconds,
            )
            response.raise_for_status()

            return True

        except Exception:
            return False
