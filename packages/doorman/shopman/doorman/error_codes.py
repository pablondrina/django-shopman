"""
Structured error codes for auth operations.

Every error path in auth services returns a specific ErrorCode,
enabling programmatic handling by API consumers and frontends.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Error codes for auth operations."""

    # Verification code errors
    RATE_LIMIT = "rate_limit"
    COOLDOWN = "cooldown"
    IP_RATE_LIMIT = "ip_rate_limit"
    SEND_FAILED = "send_failed"
    CODE_EXPIRED = "code_expired"
    CODE_INVALID = "code_invalid"
    CODE_MAX_ATTEMPTS = "code_max_attempts"

    # Access link / token errors
    TOKEN_INVALID = "token_invalid"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_USED = "token_used"

    # Customer errors
    ACCOUNT_NOT_FOUND = "account_not_found"
    ACCOUNT_INACTIVE = "account_inactive"

    # Access link email errors
    ACCESS_LINK_DISABLED = "access_link_disabled"
    INVALID_EMAIL = "invalid_email"
    EMAIL_RATE_LIMIT = "email_rate_limit"

    # General
    INVALID_INPUT = "invalid_input"
    INVALID_TARGET = "invalid_target"
