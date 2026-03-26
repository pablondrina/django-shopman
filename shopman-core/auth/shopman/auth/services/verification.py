"""
AuthService - OTP code verification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from ..conf import auth_settings, get_customer_resolver, get_auth_settings
from ..protocols.customer import AuthCustomerInfo
from ..exceptions import GateError
from ..gates import Gates
from ..models import VerificationCode
from ..signals import verification_code_sent, verification_code_verified
from ..utils import normalize_phone

if TYPE_CHECKING:
    from django.http import HttpRequest

    from ..senders import MessageSenderProtocol

logger = logging.getLogger("shopman.auth.verification")


@dataclass
class CodeRequestResult:
    """Result of code request."""

    success: bool
    code_id: str | None = None
    expires_at: str | None = None
    error: str | None = None


@dataclass
class VerifyResult:
    """Result of code verification."""

    success: bool
    customer: AuthCustomerInfo | None = None
    created_customer: bool = False
    error: str | None = None
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
        target_value = normalize_phone(target_value)

        # G9: Rate limit by target
        try:
            Gates.rate_limit(
                key=target_value,
                max_requests=auth_settings.CODE_RATE_LIMIT_MAX,
                window_minutes=auth_settings.CODE_RATE_LIMIT_WINDOW_MINUTES,
            )
        except GateError:
            return CodeRequestResult(
                success=False,
                error="Too many attempts. Please wait a few minutes.",
            )

        # G11: Cooldown between code sends
        try:
            Gates.code_cooldown(
                target_value=target_value,
                cooldown_seconds=auth_settings.MAGIC_CODE_COOLDOWN_SECONDS,
            )
        except GateError:
            return CodeRequestResult(
                success=False,
                error="Please wait before requesting a new code.",
            )

        # G10: Rate limit by IP
        if ip_address:
            try:
                Gates.ip_rate_limit(ip_address)
            except GateError:
                return CodeRequestResult(
                    success=False,
                    error="Too many attempts from this location.",
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
        sender = sender or cls._get_default_sender()
        try:
            sent = sender.send_code(target_value, raw_code, delivery_method)
            if sent:
                code.mark_sent()
            else:
                return CodeRequestResult(success=False, error="Failed to send code.")
        except Exception:
            logger.exception("Send failed", extra={"target": target_value})
            return CodeRequestResult(success=False, error="Error sending code.")

        # Signal
        verification_code_sent.send(
            sender=cls,
            code=code,
            target_value=target_value,
            delivery_method=delivery_method,
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
        target_value = normalize_phone(target_value)

        # Find valid code
        code = cls._get_valid_code(target_value, VerificationCode.Purpose.LOGIN)
        if not code:
            return VerifyResult(
                success=False,
                error="Code expired. Please request a new one.",
            )

        # Verify code via HMAC comparison
        from ..models.verification_code import verify_code

        if not verify_code(code.code_hash, code_input):
            code.record_attempt()
            return VerifyResult(
                success=False,
                error="Incorrect code.",
                attempts_remaining=code.attempts_remaining,
            )

        # Get or create Customer via resolver
        resolver = get_customer_resolver()
        customer = resolver.get_by_phone(target_value)
        created = False

        if not customer:
            # H03: Respect AUTO_CREATE_CUSTOMER setting
            if not get_auth_settings().AUTO_CREATE_CUSTOMER:
                return VerifyResult(
                    success=False,
                    error="Account not found. Please contact support.",
                )

            customer = resolver.create_for_phone(target_value)
            created = True

        # Mark code verified
        code.mark_verified(customer.uuid)

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
    def _get_default_sender(cls):
        """Get the default message sender from settings."""
        from django.utils.module_loading import import_string

        sender_class = import_string(auth_settings.MESSAGE_SENDER_CLASS)
        return sender_class()

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
