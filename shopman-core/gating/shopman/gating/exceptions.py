"""Gating exceptions."""

from typing import Any

from shopman.utils.exceptions import BaseError


class GatingError(BaseError):
    """
    Base exception for Gating.

    Usage:
        raise GatingError("TOKEN_INVALID")
        raise GatingError("RATE_LIMIT", retry_after=60)
    """

    _default_messages: dict[str, str] = {
        "TOKEN_INVALID": "Token is invalid or expired",
        "CODE_INVALID": "Code is invalid or expired",
        "RATE_LIMIT": "Rate limit exceeded",
        "GATE_FAILED": "Gate validation failed",
    }


class GateError(GatingError):
    """Gate validation error."""

    def __init__(self, gate_name: str, message: str = "", **data: Any) -> None:
        super().__init__("GATE_FAILED", message, gate_name=gate_name, **data)
        self.gate_name = gate_name
