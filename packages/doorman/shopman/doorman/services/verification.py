"""
AuthService - OTP code verification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.contrib.auth import login
from django.db import transaction
from django.utils import timezone

from ..conf import doorman_settings, get_adapter
from ..error_codes import ErrorCode
from ..protocols.customer import AuthCustomerInfo
from ..exceptions import GateError
from ..gates import Gates
from ..models import VerificationCode
from ..signals import verification_code_sent, verification_code_verified

if TYPE_CHECKING:
    from django.http import HttpRequest

    from ..senders import MessageSenderProtocol

logger = logging.getLogger("shopman.doorman.verification")


@dataclass
class CodeRequestResult:
    """Result of code request."""

    success: bool
    code_id: str | None = None
    expires_at: str | None = None
    error: str | None = None
    error_code: ErrorCode | None = None


@dataclass
class VerifyResult:
    """Result of code verification."""

    success: bool
    customer: AuthCustomerInfo | None = None
    created_customer: bool = False
    error: str | None = None
    error_code: ErrorCode | None = None
    attempts_remaining: int | None = None


class AuthService:
    """
    OTP code verification service.

    Handles code generation, sending, and verification
    for login and contact verification flows.
    """

    # ===========================================
    # Request Code
    # ===========================================

    @classmethod
    def request_code(
        cls,
        target_value: str,
        purpose: str = VerificationCode.Purpose.LOGIN,
        delivery_method: str = VerificationCode.DeliveryMethod.WHATSAPP,
        ip_address: str | None = None,
        sender: "MessageSenderProtocol | None" = None,
    ) -> CodeRequestResult:
        """
        Request a verification code.

        Args:
            target_value: Phone (E.164) or email
            purpose: Code purpose (login, verify_contact)
            delivery_method: How to send (whatsapp, sms, email)
            ip_address: Client IP for rate limiting
            sender: Custom sender (default from settings)

        Returns:
            CodeRequestResult with code_id and expiration
        """
        # Normalize target
        adapter = get_adapter()
        target_value = adapter.normalize_phone(target_value)

        # G9: Rate limit by target
        try:
            Gates.rate_limit(
                key=target_value,
                max_requests=doorman_settings.ACCESS_CODE_RATE_LIMIT_MAX,
                window_minutes=doorman_settings.ACCESS_CODE_RATE_LIMIT_WINDOW_MINUTES,
            )
        except GateError:
            return CodeRequestResult(
                success=False,
                error="Too many attempts. Please wait a few minutes.",
                error_code=ErrorCode.RATE_LIMIT,
            )

        # G11: Cooldown between code sends
        try:
            Gates.code_cooldown(
                target_value=target_value,
                cooldown_seconds=doorman_settings.ACCESS_CODE_COOLDOWN_SECONDS,
            )
        except GateError:
            return CodeRequestResult(
                success=False,
                error="Please wait before requesting a new code.",
                error_code=ErrorCode.COOLDOWN,
            )

        # G10: Rate limit by IP
        if ip_address:
            try:
                Gates.ip_rate_limit(ip_address)
            except GateError:
                return CodeRequestResult(
                    success=False,
                    error="Too many attempts from this location.",
                    error_code=ErrorCode.IP_RATE_LIMIT,
                )

        # Invalidate previous codes
        VerificationCode.objects.filter(
            target_value=target_value,
            purpose=purpose,
            status__in=[VerificationCode.Status.PENDING, VerificationCode.Status.SENT],
        ).update(status=VerificationCode.Status.EXPIRED)

        # Create code — store HMAC, send raw
        from ..models.verification_code import generate_raw_code

        raw_code, hmac_digest = generate_raw_code()
        code = VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value=target_value,
            purpose=purpose,
            delivery_method=delivery_method,
            ip_address=ip_address,
        )

        # Send raw code (not the HMAC)
        if sender:
            # Custom sender provided (e.g. tests) — bypass fallback chain
            try:
                sent = sender.send_code(target_value, raw_code, delivery_method)
                actual_method = delivery_method
                if not sent:
                    return CodeRequestResult(
                        success=False, error="Failed to send code.",
                        error_code=ErrorCode.SEND_FAILED,
                    )
            except Exception:
                logger.exception("Send failed", extra={"target": target_value})
                return CodeRequestResult(
                    success=False, error="Error sending code.",
                    error_code=ErrorCode.SEND_FAILED,
                )
        else:
            # Use adapter's fallback chain
            sent, actual_method = adapter.send_code_with_fallback(
                target_value, raw_code, preferred_method=delivery_method,
            )
            if not sent:
                return CodeRequestResult(
                    success=False, error="Failed to send code.",
                    error_code=ErrorCode.SEND_FAILED,
                )

        # Record actual delivery method used (may differ from requested)
        if actual_method != delivery_method:
            code.delivery_method = actual_method
            code.save(update_fields=["delivery_method"])

        code.mark_sent()

        # Signal
        verification_code_sent.send(
            sender=cls,
            code=code,
            target_value=target_value,
            delivery_method=actual_method,
        )

        logger.info("Code sent", extra={"target": target_value, "purpose": purpose})

        return CodeRequestResult(
            success=True,
            code_id=str(code.id),
            expires_at=code.expires_at.isoformat(),
        )

    # ===========================================
    # Verify for Login
    # ===========================================

    @classmethod
    @transaction.atomic
    def verify_for_login(
        cls,
        target_value: str,
        code_input: str,
        request: "HttpRequest | None" = None,
    ) -> VerifyResult:
        """
        Verify code for login.

        Creates or retrieves Customer and marks code as verified.

        Args:
            target_value: Phone or email
            code_input: User-provided code
            request: Django request for audit

        Returns:
            VerifyResult with customer
        """
        adapter = get_adapter()
        target_value = adapter.normalize_phone(target_value)

        # Find valid code
        code = cls._get_valid_code(target_value, VerificationCode.Purpose.LOGIN)
        if not code:
            return VerifyResult(
                success=False,
                error="Code expired. Please request a new one.",
                error_code=ErrorCode.CODE_EXPIRED,
            )

        # Verify code via HMAC comparison
        from ..models.verification_code import verify_code

        if not verify_code(code.code_hash, code_input):
            code.record_attempt()
            adapter.on_login_failed(request, target_value, "incorrect_code")
            return VerifyResult(
                success=False,
                error="Incorrect code.",
                error_code=ErrorCode.CODE_INVALID,
                attempts_remaining=code.attempts_remaining,
            )

        # Get or create Customer via adapter
        customer = adapter.resolve_customer_by_phone(target_value)
        created = False

        if not customer:
            if not adapter.should_auto_create_customer():
                adapter.on_login_failed(request, target_value, "account_not_found")
                return VerifyResult(
                    success=False,
                    error="Account not found. Please contact support.",
                    error_code=ErrorCode.ACCOUNT_NOT_FOUND,
                )

            customer = adapter.create_customer_for_phone(target_value)
            created = True

        # Mark code verified
        code.mark_verified(customer.uuid)

        # Django login if request provided
        if request is not None:
            from ._user_bridge import get_or_create_user_for_customer

            # Preserve session keys across login (login flushes session)
            preserved = {}
            preserve_keys = doorman_settings.PRESERVE_SESSION_KEYS
            if preserve_keys and hasattr(request, "session"):
                for key in preserve_keys:
                    if key in request.session:
                        preserved[key] = request.session[key]

            user, _ = get_or_create_user_for_customer(customer)
            login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")

            # Restore preserved keys
            for key, val in preserved.items():
                request.session[key] = val

        # Signal
        verification_code_verified.send(
            sender=cls,
            code=code,
            customer=customer,
            purpose=VerificationCode.Purpose.LOGIN,
        )

        logger.info(
            "Login verified",
            extra={
                "customer_id": str(customer.uuid),
                "created_customer": created,
            },
        )

        return VerifyResult(
            success=True,
            customer=customer,
            created_customer=created,
        )

    # ===========================================
    # Helpers
    # ===========================================

    @classmethod
    def _get_valid_code(cls, target_value: str, purpose: str) -> VerificationCode | None:
        """Get the most recent valid code for target and purpose."""
        try:
            return VerificationCode.objects.filter(
                target_value=target_value,
                purpose=purpose,
                status__in=[VerificationCode.Status.PENDING, VerificationCode.Status.SENT],
                expires_at__gt=timezone.now(),
            ).latest("created_at")
        except VerificationCode.DoesNotExist:
            return None

    @classmethod
    def cleanup_expired_codes(cls, days: int = 7) -> int:
        """
        Delete expired codes older than N days.

        Args:
            days: Delete codes older than this many days

        Returns:
            Number of deleted codes
        """
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = VerificationCode.objects.filter(
            expires_at__lt=cutoff,
        ).delete()
        return deleted
