"""
Tests for shopman.orderman.exceptions module.
"""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.exceptions import (
    CommitError,
    DirectiveError,
    IdempotencyError,
    InvalidTransition,
    IssueResolveError,
    OrderError,
    SessionError,
    ValidationError,
)


class OrderErrorTests(TestCase):
    """Tests for base OrderError."""

    def test_ordering_error_is_exception(self) -> None:
        """Should be an Exception subclass."""
        error = OrderError("test")
        self.assertIsInstance(error, Exception)


class ValidationErrorTests(TestCase):
    """Tests for ValidationError."""

    def test_validation_error_attributes(self) -> None:
        """Should store code, message, and context."""
        error = ValidationError(
            code="invalid_field",
            message="Field is invalid",
            context={"field": "email"},
        )
        self.assertEqual(error.code, "invalid_field")
        self.assertEqual(error.message, "Field is invalid")
        self.assertEqual(error.context, {"field": "email"})

    def test_validation_error_default_context(self) -> None:
        """Should default context to empty dict."""
        error = ValidationError(code="test", message="test")
        self.assertEqual(error.context, {})


class SessionErrorTests(TestCase):
    """Tests for SessionError."""

    def test_session_error_attributes(self) -> None:
        """Should store code, message, and context."""
        error = SessionError(
            code="not_found",
            message="Session not found",
            context={"session_key": "ABC123"},
        )
        self.assertEqual(error.code, "not_found")
        self.assertEqual(error.message, "Session not found")
        self.assertEqual(error.context, {"session_key": "ABC123"})


class CommitErrorTests(TestCase):
    """Tests for CommitError."""

    def test_commit_error_attributes(self) -> None:
        """Should store code, message, and context."""
        error = CommitError(
            code="blocking_issues",
            message="Has blocking issues",
            context={"issues": [{"id": "ISS-1"}]},
        )
        self.assertEqual(error.code, "blocking_issues")
        self.assertEqual(error.message, "Has blocking issues")
        self.assertIn("issues", error.context)


class DirectiveErrorTests(TestCase):
    """Tests for DirectiveError."""

    def test_directive_error_attributes(self) -> None:
        """Should store code, message, and context."""
        error = DirectiveError(
            code="no_handler",
            message="No handler registered",
            context={"topic": "unknown.topic"},
        )
        self.assertEqual(error.code, "no_handler")
        self.assertEqual(error.message, "No handler registered")
        self.assertEqual(error.context, {"topic": "unknown.topic"})

    def test_directive_error_default_context(self) -> None:
        """Should default context to empty dict."""
        error = DirectiveError(code="test", message="test")
        self.assertEqual(error.context, {})


class IssueResolveErrorTests(TestCase):
    """Tests for IssueResolveError."""

    def test_issue_resolve_error_attributes(self) -> None:
        """Should store code, message, and context."""
        error = IssueResolveError(
            code="issue_not_found",
            message="Issue not found",
            context={"issue_id": "ISS-123"},
        )
        self.assertEqual(error.code, "issue_not_found")
        self.assertEqual(error.context, {"issue_id": "ISS-123"})


class IdempotencyErrorTests(TestCase):
    """Tests for IdempotencyError."""

    def test_idempotency_error_attributes(self) -> None:
        """Should store code, message, and context."""
        error = IdempotencyError(
            code="in_progress",
            message="Operation in progress",
            context={"key": "commit-123"},
        )
        self.assertEqual(error.code, "in_progress")
        self.assertEqual(error.message, "Operation in progress")
        self.assertEqual(error.context, {"key": "commit-123"})

    def test_idempotency_error_default_context(self) -> None:
        """Should default context to empty dict."""
        error = IdempotencyError(code="test", message="test")
        self.assertEqual(error.context, {})


class InvalidTransitionTests(TestCase):
    """Tests for InvalidTransition."""

    def test_invalid_transition_attributes(self) -> None:
        """Should store code, message, and context."""
        error = InvalidTransition(
            code="invalid_transition",
            message="Cannot transition",
            context={"from": "new", "to": "completed"},
        )
        self.assertEqual(error.code, "invalid_transition")
        self.assertIn("from", error.context)
