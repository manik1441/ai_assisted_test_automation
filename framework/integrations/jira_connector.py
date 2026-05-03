"""Jira Connector — read and optionally write back to Jira.

Toggle behaviour via config.yaml:
    jira:
      write_back: false   # read-only
      write_back: true    # read + post test results back to the ticket

Required environment variables:
    JIRA_BASE_URL      — e.g. https://mycompany.atlassian.net
    JIRA_EMAIL         — Atlassian account email
    JIRA_API_TOKEN     — API token from id.atlassian.com

Usage:
    connector = JiraConnector(config.jira)
    ticket = connector.get_ticket("QA-123")
    if config.jira.write_back:
        connector.post_test_results("QA-123", summary, passed=True)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from jira import JIRA, JIRAError

from framework.core.config import JiraConfig
from framework.core.exceptions import JiraConnectorError

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Value objects
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class JiraTicket:
    ticket_id: str
    summary: str
    description: str
    acceptance_criteria: str
    status: str
    issue_type: str
    labels: list[str]


# ──────────────────────────────────────────────────────────────────────────────
# Connector
# ──────────────────────────────────────────────────────────────────────────────

class JiraConnector:
    """Wraps the `jira` library for ATF read/write operations.

    Read operations are always available when jira.enabled = true.
    Write operations (post_test_results, add_comment) require write_back = true.
    """

    def __init__(self, config: JiraConfig) -> None:
        self._config = config
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # Client construction
    # ------------------------------------------------------------------

    def _build_client(self) -> JIRA:
        base_url = self._config.base_url or os.getenv("JIRA_BASE_URL", "")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_API_TOKEN", "")

        if not all([base_url, email, token]):
            raise JiraConnectorError(
                "Jira credentials are incomplete.",
                details={
                    "missing": [
                        k for k, v in {
                            "JIRA_BASE_URL": base_url,
                            "JIRA_EMAIL": email,
                            "JIRA_API_TOKEN": token,
                        }.items() if not v
                    ]
                },
            )

        try:
            client = JIRA(
                server=base_url,
                basic_auth=(email, token),
            )
            logger.info("Jira client connected to: %s", base_url)
            return client
        except JIRAError as exc:
            raise JiraConnectorError(
                f"Failed to connect to Jira: {exc.text}",
                details={"status_code": exc.status_code},
            ) from exc

    # ------------------------------------------------------------------
    # Read operations (always available)
    # ------------------------------------------------------------------

    def get_ticket(self, ticket_id: str) -> dict:
        """Fetch a Jira ticket and return a normalised dict.

        Returns:
            {
                "summary": str,
                "description": str,
                "acceptance_criteria": str,
                "status": str,
                "issue_type": str,
                "labels": list[str],
            }
        """
        try:
            issue = self._client.issue(ticket_id)
        except JIRAError as exc:
            raise JiraConnectorError(
                f"Failed to fetch ticket {ticket_id}: {exc.text}",
                details={"ticket_id": ticket_id, "status_code": exc.status_code},
            ) from exc

        fields = issue.fields
        description = getattr(fields, "description", "") or ""
        acceptance_criteria = self._extract_acceptance_criteria(
            description, fields
        )

        return {
            "summary": getattr(fields, "summary", "") or "",
            "description": description,
            "acceptance_criteria": acceptance_criteria,
            "status": str(getattr(fields.status, "name", "")) if fields.status else "",
            "issue_type": str(getattr(fields.issuetype, "name", "")) if fields.issuetype else "",
            "labels": list(getattr(fields, "labels", [])),
        }

    def get_tickets_by_project(
        self, project_key: str, max_results: int = 50
    ) -> list[dict]:
        """Fetch open tickets from a project (for batch test generation)."""
        jql = (
            f"project = {project_key} "
            "AND issuetype in (Story, Bug, Task) "
            "AND status != Done "
            "ORDER BY priority ASC"
        )
        try:
            issues = self._client.search_issues(jql, maxResults=max_results)
        except JIRAError as exc:
            raise JiraConnectorError(
                f"JQL search failed: {exc.text}",
                details={"jql": jql},
            ) from exc

        return [self.get_ticket(issue.key) for issue in issues]

    # ------------------------------------------------------------------
    # Write operations (require write_back = true)
    # ------------------------------------------------------------------

    def post_test_results(
        self,
        ticket_id: str,
        summary_dict: dict,
        *,
        passed: bool,
    ) -> None:
        """Post a test result comment to a Jira ticket.

        Raises JiraConnectorError if write_back is disabled.
        """
        self._assert_write_enabled()

        total = summary_dict.get("execution", {}).get("total", 0)
        pass_count = summary_dict.get("execution", {}).get("passed", 0)
        failed_count = summary_dict.get("execution", {}).get("failed", 0)
        pass_rate = summary_dict.get("execution", {}).get("pass_rate_percent", 0)
        status_icon = "✅" if passed else "❌"

        comment_body = (
            f"{status_icon} *ATF Automated Test Results*\n\n"
            f"*Status:* {'PASSED' if passed else 'FAILED'}\n"
            f"*Total:* {total} | *Passed:* {pass_count} | *Failed:* {failed_count}\n"
            f"*Pass Rate:* {pass_rate}%\n\n"
            f"_Generated by Agentic TestGen Framework (ATF)_"
        )

        try:
            self._client.add_comment(ticket_id, comment_body)
            logger.info(
                "Test results posted to Jira ticket: %s", ticket_id
            )
        except JIRAError as exc:
            raise JiraConnectorError(
                f"Failed to post comment to {ticket_id}: {exc.text}",
                details={"ticket_id": ticket_id},
            ) from exc

    def add_comment(self, ticket_id: str, comment: str) -> None:
        """Post a free-form comment to a Jira ticket.

        Requires write_back = true.
        """
        self._assert_write_enabled()
        try:
            self._client.add_comment(ticket_id, comment)
            logger.info("Comment added to Jira ticket: %s", ticket_id)
        except JIRAError as exc:
            raise JiraConnectorError(
                f"Failed to add comment to {ticket_id}: {exc.text}"
            ) from exc

    def transition_ticket(self, ticket_id: str, transition_name: str) -> None:
        """Transition a ticket to a new status (e.g., 'In Testing').

        Requires write_back = true.
        """
        self._assert_write_enabled()
        try:
            transitions = self._client.transitions(ticket_id)
            target = next(
                (t for t in transitions if t["name"].lower() == transition_name.lower()),
                None,
            )
            if not target:
                raise JiraConnectorError(
                    f"Transition '{transition_name}' not found for {ticket_id}.",
                    details={"available": [t["name"] for t in transitions]},
                )
            self._client.transition_issue(ticket_id, target["id"])
            logger.info(
                "Ticket %s transitioned to: %s", ticket_id, transition_name
            )
        except JIRAError as exc:
            raise JiraConnectorError(
                f"Failed to transition {ticket_id}: {exc.text}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_write_enabled(self) -> None:
        """Raise JiraConnectorError if write_back is disabled."""
        if not self._config.write_back:
            raise JiraConnectorError(
                "Jira write operations are disabled. "
                "Set jira.write_back: true in config.yaml to enable.",
                details={"current_write_back": self._config.write_back},
            )

    @staticmethod
    def _extract_acceptance_criteria(description: str, fields: object) -> str:
        """Attempt to extract Acceptance Criteria from description text.

        Jira doesn't have a standard AC field — look for common headers.
        """
        if not description:
            return ""

        ac_headers = [
            "acceptance criteria",
            "acceptance criterion",
            "ac:",
            "given ",
        ]
        lines = description.splitlines()
        capturing = False
        ac_lines: list[str] = []

        for line in lines:
            lower = line.lower().strip()
            if any(lower.startswith(h) for h in ac_headers):
                capturing = True
            if capturing:
                ac_lines.append(line)

        return "\n".join(ac_lines).strip() or ""
