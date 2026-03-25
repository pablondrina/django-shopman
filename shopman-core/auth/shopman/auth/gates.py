"""
Auth Gates - Validation rules.

G7: BridgeTokenValidity - Token is valid for exchange
G8: MagicCodeValidity - Code is valid for verification
G9: RateLimit - Rate limiting for code requests
G10: IPRateLimit - Rate limiting by IP address
G11: CodeCooldown - Minimum time between code sends
G12: MagicLinkRateLimit - Rate limiting for magic link requests
"""

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from .exceptions import GateError
from .models import BridgeToken, MagicCode


@dataclass
class GateResult:
    """Result of a gate check."""

    passed: bool
    gate_name: str
    message: str = ""


class Gates:
    """Auth validation gates."""

    # ===========================================
    # G7: Bridge Token Validity
    # ===========================================

    # Janela de reuso do token (segundos) - para lidar com prefetch de navegadores
    BRIDGE_TOKEN_REUSE_WINDOW_SECONDS = 60

    @classmethod
    def bridge_token_validity(
        cls,
        token: BridgeToken,
        required_audience: str | None = None,
    ) -> GateResult:
        """
        G7: Token is valid for exchange.

        Args:
            token: BridgeToken instance
            required_audience: If set, token must have this audience

        Raises:
            GateError: If token is invalid
        """
        if token.used_at:
            # Permite reuso dentro da janela (para lidar com prefetch de navegadores)
            reuse_window = timedelta(seconds=cls.BRIDGE_TOKEN_REUSE_WINDOW_SECONDS)
            if timezone.now() - token.used_at > reuse_window:
                raise GateError("G7_BridgeTokenValidity", "Token already used.")

        if token.is_expired:
            raise GateError("G7_BridgeTokenValidity", "Token expired.")

        if required_audience and token.audience != required_audience:
            raise GateError(
                "G7_BridgeTokenValidity",
                f"Wrong audience: expected {required_audience}",
            )

        return GateResult(True, "G7_BridgeTokenValidity")

    @classmethod
    def check_bridge_token_validity(
        cls,
        token: BridgeToken,
        required_audience: str | None = None,
    ) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.bridge_token_validity(token, required_audience)
            return True
        except GateError:
            return False

    # ===========================================
    # G8: Magic Code Validity
    # ===========================================

    @classmethod
    def magic_code_validity(cls, code: MagicCode) -> GateResult:
        """
        G8: Code is valid for verification.

        Args:
            code: MagicCode instance

        Raises:
            GateError: If code is invalid
        """
        if not code.is_valid:
            if code.is_expired:
                raise GateError("G8_MagicCodeValidity", "Code expired.")
            if code.attempts >= code.max_attempts:
                raise GateError("G8_MagicCodeValidity", "Max attempts exceeded.")
            if code.status == MagicCode.Status.VERIFIED:
                raise GateError("G8_MagicCodeValidity", "Code already verified.")
            raise GateError("G8_MagicCodeValidity", "Code invalid.")

        return GateResult(True, "G8_MagicCodeValidity")

    @classmethod
    def check_magic_code_validity(cls, code: MagicCode) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.magic_code_validity(code)
            return True
        except GateError:
            return False

    # ===========================================
    # G9: Rate Limit
    # ===========================================

    @classmethod
    def rate_limit(
        cls,
        key: str,
        max_requests: int,
        window_minutes: int,
    ) -> GateResult:
        """
        G9: Rate limiting for code requests.

        Args:
            key: Rate limit key (typically phone/email)
            max_requests: Maximum requests allowed
            window_minutes: Time window in minutes

        Raises:
            GateError: If rate limit exceeded
        """
        window_start = timezone.now() - timedelta(minutes=window_minutes)

        count = MagicCode.objects.filter(
            target_value=key,
            created_at__gte=window_start,
        ).count()

        if count >= max_requests:
            raise GateError(
                "G9_RateLimit",
                f"Rate limit: {count}/{max_requests} in {window_minutes}min.",
            )

        return GateResult(True, "G9_RateLimit")

    @classmethod
    def check_rate_limit(
        cls,
        key: str,
        max_requests: int,
        window_minutes: int,
    ) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.rate_limit(key, max_requests, window_minutes)
            return True
        except GateError:
            return False

    # ===========================================
    # G10: IP Rate Limit (bonus)
    # ===========================================

    @classmethod
    def ip_rate_limit(
        cls,
        ip_address: str,
        max_requests: int = 20,
        window_minutes: int = 60,
    ) -> GateResult:
        """
        G10: Rate limiting by IP address.

        Args:
            ip_address: Client IP address
            max_requests: Maximum requests allowed
            window_minutes: Time window in minutes

        Raises:
            GateError: If rate limit exceeded
        """
        if not ip_address:
            return GateResult(True, "G10_IPRateLimit", "No IP provided")

        window_start = timezone.now() - timedelta(minutes=window_minutes)

        count = MagicCode.objects.filter(
            ip_address=ip_address,
            created_at__gte=window_start,
        ).count()

        if count >= max_requests:
            raise GateError(
                "G10_IPRateLimit",
                f"IP rate limit: {count}/{max_requests} in {window_minutes}min.",
            )

        return GateResult(True, "G10_IPRateLimit")

    # ===========================================
    # G11: Code Send Cooldown
    # ===========================================

    @classmethod
    def code_cooldown(
        cls,
        target_value: str,
        cooldown_seconds: int,
    ) -> GateResult:
        """
        G11: Minimum time between code sends to same target.

        Prevents rapid-fire code requests that waste messaging credits
        and confuse the user (only the last code works).

        Args:
            target_value: Phone/email
            cooldown_seconds: Minimum seconds between sends

        Raises:
            GateError: If cooldown period not elapsed
        """
        last_code = (
            MagicCode.objects.filter(target_value=target_value)
            .order_by("-created_at")
            .first()
        )

        if last_code:
            elapsed = (timezone.now() - last_code.created_at).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = int(cooldown_seconds - elapsed)
                raise GateError(
                    "G11_CodeCooldown",
                    f"Please wait {remaining}s before requesting a new code.",
                )

        return GateResult(True, "G11_CodeCooldown")

    # ===========================================
    # G12: Magic Link Rate Limit
    # ===========================================

    @classmethod
    def magic_link_rate_limit(
        cls,
        email: str,
        max_requests: int,
        window_minutes: int,
    ) -> GateResult:
        """
        G12: Rate limiting for magic link requests per email.

        Prevents email bombing by limiting how many magic links
        can be sent to the same address within a time window.

        Args:
            email: Target email address
            max_requests: Maximum requests allowed
            window_minutes: Time window in minutes

        Raises:
            GateError: If rate limit exceeded
        """
        window_start = timezone.now() - timedelta(minutes=window_minutes)

        count = BridgeToken.objects.filter(
            metadata__method="magic_link",
            metadata__email=email,
            created_at__gte=window_start,
        ).count()

        if count >= max_requests:
            raise GateError(
                "G12_MagicLinkRateLimit",
                f"Rate limit: {count}/{max_requests} in {window_minutes}min.",
            )

        return GateResult(True, "G12_MagicLinkRateLimit")

    @classmethod
    def check_magic_link_rate_limit(
        cls,
        email: str,
        max_requests: int,
        window_minutes: int,
    ) -> bool:
        """Check without raising (returns bool)."""
        try:
            cls.magic_link_rate_limit(email, max_requests, window_minutes)
            return True
        except GateError:
            return False
