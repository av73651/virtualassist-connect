"""Manual Validation: Test Jira integration against real instance.

Usage:
    export JIRA_EMAIL="your-email@example.com"
    export JIRA_API_TOKEN="your-api-token"
    python scripts/validate_jira.py

This creates a test ticket in ASD project, adds a comment, attaches a file,
and prints the ticket URL for manual verification."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import Mock
from src.repositories.integration_repository import IntegrationRepository

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), ".jira_credentials.json")


def main():
    # Try credentials file first, then env vars
    email = None
    api_token = None

    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE) as f:
            creds = json.load(f)
        email = creds.get("email")
        api_token = creds.get("api_token")

    email = email or os.environ.get("JIRA_EMAIL")
    api_token = api_token or os.environ.get("JIRA_API_TOKEN")

    if not email or not api_token or email == "your-email@example.com":
        print("ERROR: Provide Jira credentials.")
        print(f"  Option 1: Edit {CREDENTIALS_FILE}")
        print("  Option 2: export JIRA_EMAIL and JIRA_API_TOKEN")
        sys.exit(1)

    # Mock Secrets Manager to return env credentials
    mock_secrets = Mock()
    mock_secrets.get_secret_value.return_value = {
        "SecretString": f'{{"email": "{email}", "api_token": "{api_token}"}}'
    }

    repo = IntegrationRepository(
        jira_url="https://rameshnag2002.atlassian.net",
        jira_project_key="ASD",
        secrets_client=mock_secrets,
    )

    # Step 1: Create ticket
    print("\n[1/3] Creating Jira ticket...")
    ticket_key = repo.create_jira_ticket(
        summary="[SEV-1] calculator (prod): Error rate exceeds threshold [TEST]",
        description="Incident detected. Automated triage in progress. This is a test ticket from T2 validation.",
        priority="SEV-1",
        labels=["incident", "automated", "calculator", "prod", "test"],
        incident_key="calculator-error-rate-prod",
    )

    if not ticket_key:
        print("FAILED: Could not create Jira ticket.")
        sys.exit(1)

    print(f"  OK: Created {ticket_key}")
    print(f"  URL: https://rameshnag2002.atlassian.net/browse/{ticket_key}")

    # Step 2: Add comment
    print("\n[2/3] Adding comment...")
    ok = repo.add_jira_comment(
        ticket_key,
        "Incident detected at 2026-03-30T12:00:00Z. Automated analysis starting. "
        "Root cause classified as bad-deployment (high confidence). "
        "Blast radius: 50 users affected, 15% error rate on /api/calculate.",
    )
    print(f"  {'OK' if ok else 'FAILED'}: Comment {'added' if ok else 'failed'}")

    # Step 3: Attach file
    print("\n[3/3] Attaching log file...")
    log_content = (
        "2026-03-30T12:00:01Z ERROR calculator /api/calculate DivisionByZeroError\n"
        "2026-03-30T12:00:02Z ERROR calculator /api/calculate DivisionByZeroError\n"
        "2026-03-30T12:00:03Z ERROR calculator /api/calculate DivisionByZeroError\n"
        "2026-03-30T12:00:04Z ERROR calculator /api/calculate DivisionByZeroError\n"
        "2026-03-30T12:00:05Z ERROR calculator /api/calculate DivisionByZeroError\n"
    )
    ok = repo.attach_jira_file(ticket_key, "error-logs-2026-03-30.txt", log_content)
    print(f"  {'OK' if ok else 'FAILED'}: File {'attached' if ok else 'failed'}")

    print(f"\n{'='*60}")
    print(f"VALIDATION COMPLETE")
    print(f"Ticket: https://rameshnag2002.atlassian.net/browse/{ticket_key}")
    print(f"Please verify in Jira UI:")
    print(f"  - Summary: [SEV-1] calculator (prod): Error rate exceeds threshold [TEST]")
    print(f"  - Priority: Highest")
    print(f"  - Labels: incident, automated, calculator, prod, test")
    print(f"  - Comment with analysis details")
    print(f"  - Attached file: error-logs-2026-03-30.txt")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
