"""Tests for TicketingRepository + EventBusRepository — Jira CRUD + EventBridge publish."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.repositories.ticketing_repository import TicketingRepository
from src.repositories.event_bus_repository import EventBusRepository


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_secrets_client():
    """Mock Secrets Manager client returning Jira credentials."""
    client = Mock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps({
            "email": "incident-bot@example.com",
            "api_token": "test-api-token-123",
            "account_id": "5f1234567890abcdef012345",
        })
    }
    return client


@pytest.fixture
def mock_eventbridge_client():
    """Mock EventBridge client."""
    client = Mock()
    client.put_events.return_value = {"FailedEntryCount": 0}
    return client


@pytest.fixture
def repo(mock_secrets_client, incident_config):
    """TicketingRepository with mocked clients."""
    return TicketingRepository(
        config=incident_config,
        jira_url="https://test-instance.atlassian.net",
        jira_project_key="ASD",
        secrets_client=mock_secrets_client,
    )


@pytest.fixture
def event_bus_repo(mock_eventbridge_client, incident_config):
    """EventBusRepository with mocked client."""
    return EventBusRepository(
        config=incident_config,
        eventbridge_client=mock_eventbridge_client,
    )


# ------------------------------------------------------------------ #
# Credentials
# ------------------------------------------------------------------ #

class TestJiraCredentials:
    """Jira credentials loaded from Secrets Manager."""

    def test_credentials_from_secrets_manager(self, repo, mock_secrets_client):
        """Credentials loaded from Secrets Manager on first call (AC-048)."""
        creds = repo._get_credentials()

        mock_secrets_client.get_secret_value.assert_called_once_with(
            SecretId="sre-platform/jira-credentials"
        )
        assert creds["email"] == "incident-bot@example.com"
        assert creds["api_token"] == "test-api-token-123"

    def test_credentials_cached_after_first_call(self, repo, mock_secrets_client):
        """Credentials cached — Secrets Manager called only once."""
        repo._get_credentials()
        repo._get_credentials()

        mock_secrets_client.get_secret_value.assert_called_once()


# ------------------------------------------------------------------ #
# Create Ticket
# ------------------------------------------------------------------ #

class TestCreateJiraTicket:
    """Jira ticket creation."""

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_success(self, mock_post, repo):
        """Creates ticket with correct fields, returns ticket key (AC-013)."""
        mock_post.return_value = Mock(
            status_code=201,
            json=lambda: {"key": "ASD-101"},
        )
        mock_post.return_value.raise_for_status = Mock()

        result = repo.create_jira_ticket(
            summary="[SEV-1] calculator (prod): Error rate exceeds threshold",
            description="Incident detected. Automated triage in progress...",
            priority="SEV-1",
            labels=["incident", "automated", "calculator", "prod"],
            incident_key="calculator-error-rate-prod",
        )

        assert result == "ASD-101"

        # Verify request
        call_args = mock_post.call_args
        assert "rest/api/3/issue" in call_args.args[0]

        payload = call_args.kwargs["json"]
        assert payload["fields"]["project"]["key"] == "ASD"
        assert payload["fields"]["priority"]["name"] == "Highest"
        assert payload["fields"]["labels"] == ["incident", "automated", "calculator", "prod"]
        assert payload["fields"]["issuetype"]["name"] == "Incident"
        assert payload["fields"]["reporter"] == {"accountId": "5f1234567890abcdef012345"}

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_sev2_priority(self, mock_post, repo):
        """SEV-2 maps to High priority."""
        mock_post.return_value = Mock(
            status_code=201,
            json=lambda: {"key": "ASD-102"},
        )
        mock_post.return_value.raise_for_status = Mock()

        repo.create_jira_ticket(
            summary="[SEV-2] calculator (prod): Latency",
            description="Test",
            priority="SEV-2",
            labels=["incident"],
            incident_key="calculator-latency-prod",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["fields"]["priority"]["name"] == "High"

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_sev3_priority(self, mock_post, repo):
        """SEV-3 maps to Medium priority."""
        mock_post.return_value = Mock(
            status_code=201,
            json=lambda: {"key": "ASD-103"},
        )
        mock_post.return_value.raise_for_status = Mock()

        repo.create_jira_ticket(
            summary="[SEV-3] calculator (prod): 4xx errors",
            description="Test",
            priority="SEV-3",
            labels=["incident"],
            incident_key="calculator-4xx-errors-prod",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["fields"]["priority"]["name"] == "Medium"

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_failure_returns_none(self, mock_post, repo):
        """Jira failure returns None (AC-050, P6, P10)."""
        mock_post.side_effect = Exception("Connection refused")

        result = repo.create_jira_ticket(
            summary="Test",
            description="Test",
            priority="SEV-1",
            labels=[],
            incident_key="test-key",
        )

        assert result is None

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_http_error_returns_none(self, mock_post, repo):
        """HTTP 500 returns None."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("500 Server Error")
        mock_post.return_value = mock_response

        result = repo.create_jira_ticket(
            summary="Test",
            description="Test",
            priority="SEV-1",
            labels=[],
            incident_key="test-key",
        )

        assert result is None

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_uses_basic_auth(self, mock_post, repo):
        """Request uses basic auth from Secrets Manager."""
        mock_post.return_value = Mock(
            status_code=201,
            json=lambda: {"key": "ASD-104"},
        )
        mock_post.return_value.raise_for_status = Mock()

        repo.create_jira_ticket(
            summary="Test",
            description="Test",
            priority="SEV-1",
            labels=[],
            incident_key="test-key",
        )

        call_args = mock_post.call_args
        assert call_args.kwargs["auth"] == ("incident-bot@example.com", "test-api-token-123")

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_reporter_set_from_credentials(self, mock_post, repo):
        """Reporter set to service account from credentials (AC-013)."""
        mock_post.return_value = Mock(
            status_code=201,
            json=lambda: {"key": "ASD-106"},
        )
        mock_post.return_value.raise_for_status = Mock()

        repo.create_jira_ticket(
            summary="Test",
            description="Test",
            priority="SEV-1",
            labels=[],
            incident_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["fields"]["reporter"] == {"accountId": "5f1234567890abcdef012345"}

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_no_reporter_when_account_id_missing(self, mock_post, incident_config):
        """No reporter field when account_id absent from credentials."""
        secrets_client = Mock()
        secrets_client.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "email": "incident-bot@example.com",
                "api_token": "test-api-token-123",
            })
        }
        repo = TicketingRepository(
            config=incident_config,
            jira_url="https://test-instance.atlassian.net",
            secrets_client=secrets_client,
        )

        mock_post.return_value = Mock(
            status_code=201,
            json=lambda: {"key": "ASD-107"},
        )
        mock_post.return_value.raise_for_status = Mock()

        repo.create_jira_ticket(
            summary="Test",
            description="Test",
            priority="SEV-1",
            labels=[],
            incident_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert "reporter" not in payload["fields"]

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_create_ticket_description_adf_format(self, mock_post, repo):
        """Description uses Atlassian Document Format (ADF)."""
        mock_post.return_value = Mock(
            status_code=201,
            json=lambda: {"key": "ASD-105"},
        )
        mock_post.return_value.raise_for_status = Mock()

        repo.create_jira_ticket(
            summary="Test",
            description="Incident detected. Automated triage in progress...",
            priority="SEV-1",
            labels=[],
            incident_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        desc = payload["fields"]["description"]
        assert desc["type"] == "doc"
        assert desc["version"] == 1
        assert desc["content"][0]["content"][0]["text"] == "Incident detected. Automated triage in progress..."


# ------------------------------------------------------------------ #
# Add Comment
# ------------------------------------------------------------------ #

class TestAddJiraComment:
    """Jira comment operations."""

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_add_comment_success(self, mock_post, repo):
        """Comment added successfully, returns True."""
        mock_post.return_value = Mock(status_code=201)
        mock_post.return_value.raise_for_status = Mock()

        result = repo.add_jira_comment("ASD-101", "Triage started.")

        assert result is True
        assert "ASD-101/comment" in mock_post.call_args.args[0]

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_add_comment_adf_format(self, mock_post, repo):
        """Comment body uses ADF format."""
        mock_post.return_value = Mock(status_code=201)
        mock_post.return_value.raise_for_status = Mock()

        repo.add_jira_comment("ASD-101", "Analysis complete.")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["body"]["type"] == "doc"
        assert payload["body"]["content"][0]["content"][0]["text"] == "Analysis complete."

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_add_comment_failure_returns_false(self, mock_post, repo):
        """Comment failure returns False."""
        mock_post.side_effect = Exception("Connection refused")

        result = repo.add_jira_comment("ASD-101", "Test")

        assert result is False


# ------------------------------------------------------------------ #
# Attach File
# ------------------------------------------------------------------ #

class TestAttachJiraFile:
    """Jira file attachment operations."""

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_attach_file_success(self, mock_post, repo):
        """File attached successfully, returns True."""
        mock_post.return_value = Mock(status_code=200)
        mock_post.return_value.raise_for_status = Mock()

        result = repo.attach_jira_file(
            "ASD-101", "error-logs-2026-03-30.txt", "ERROR: DivisionByZero..."
        )

        assert result is True
        assert "ASD-101/attachments" in mock_post.call_args.args[0]

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_attach_file_no_check_header(self, mock_post, repo):
        """Attachment uses X-Atlassian-Token: no-check header."""
        mock_post.return_value = Mock(status_code=200)
        mock_post.return_value.raise_for_status = Mock()

        repo.attach_jira_file("ASD-101", "logs.txt", "content")

        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Atlassian-Token"] == "no-check"

    @patch("src.repositories.ticketing_repository.requests.post")
    def test_attach_file_failure_returns_false(self, mock_post, repo):
        """Attachment failure returns False."""
        mock_post.side_effect = Exception("Timeout")

        result = repo.attach_jira_file("ASD-101", "logs.txt", "content")

        assert result is False


# ------------------------------------------------------------------ #
# Transition Ticket
# ------------------------------------------------------------------ #

class TestTransitionJiraTicket:
    """Jira ticket status transitions."""

    @patch("src.repositories.ticketing_repository.requests.post")
    @patch("src.repositories.ticketing_repository.requests.get")
    def test_transition_success(self, mock_get, mock_post, repo):
        """Ticket transitioned successfully, returns True."""
        # GET transitions
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "transitions": [
                    {"id": "21", "name": "In Progress"},
                    {"id": "31", "name": "Done"},
                ]
            },
        )
        mock_get.return_value.raise_for_status = Mock()

        # POST transition
        mock_post.return_value = Mock(status_code=204)
        mock_post.return_value.raise_for_status = Mock()

        result = repo.transition_jira_ticket("ASD-101", "Done")

        assert result is True
        post_payload = mock_post.call_args.kwargs["json"]
        assert post_payload["transition"]["id"] == "31"

    @patch("src.repositories.ticketing_repository.requests.get")
    def test_transition_not_found(self, mock_get, repo):
        """Transition name not available returns False."""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "transitions": [
                    {"id": "21", "name": "In Progress"},
                ]
            },
        )
        mock_get.return_value.raise_for_status = Mock()

        result = repo.transition_jira_ticket("ASD-101", "Resolved")

        assert result is False

    @patch("src.repositories.ticketing_repository.requests.post")
    @patch("src.repositories.ticketing_repository.requests.get")
    def test_transition_case_insensitive(self, mock_get, mock_post, repo):
        """Transition name matching is case-insensitive."""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "transitions": [{"id": "31", "name": "Done"}]
            },
        )
        mock_get.return_value.raise_for_status = Mock()
        mock_post.return_value = Mock(status_code=204)
        mock_post.return_value.raise_for_status = Mock()

        result = repo.transition_jira_ticket("ASD-101", "done")

        assert result is True

    @patch("src.repositories.ticketing_repository.requests.get")
    def test_transition_failure_returns_false(self, mock_get, repo):
        """Transition API failure returns False."""
        mock_get.side_effect = Exception("Connection refused")

        result = repo.transition_jira_ticket("ASD-101", "Done")

        assert result is False


# ------------------------------------------------------------------ #
# Publish Event (EventBridge)
# ------------------------------------------------------------------ #

class TestPublishEvent:
    """EventBridge event publishing."""

    def test_publish_event_success(self, event_bus_repo, mock_eventbridge_client):
        """Publishes event to EventBridge, returns True."""
        detail = {
            "incident_key": "calculator-error-rate-prod",
            "jira_ticket_id": "INC-142",
        }

        result = event_bus_repo.publish_event("IncidentCreated", detail)

        assert result is True
        mock_eventbridge_client.put_events.assert_called_once()

    def test_publish_event_correct_format(self, event_bus_repo, mock_eventbridge_client):
        """Event entry has correct source, detail-type, and detail."""
        detail = {"incident_key": "calc-error-rate-prod", "severity": "SEV-1"}

        event_bus_repo.publish_event("IncidentCreated", detail)

        entry = mock_eventbridge_client.put_events.call_args[1]["Entries"][0]
        assert entry["Source"] == "sre-platform"
        assert entry["DetailType"] == "IncidentCreated"
        assert '"incident_key": "calc-error-rate-prod"' in entry["Detail"]

    def test_publish_event_failure_returns_false(self, event_bus_repo, mock_eventbridge_client):
        """EventBridge failure returns False (P10)."""
        mock_eventbridge_client.put_events.side_effect = Exception("Timeout")

        result = event_bus_repo.publish_event("IncidentCreated", {})

        assert result is False
