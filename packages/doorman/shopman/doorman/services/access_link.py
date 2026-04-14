"""
AccessLinkService - Access link authentication.

Handles both chat-to-web tokens and email-based access links.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from ..conf import doorman_settings, get_adapter, get_doorman_settings
from ..error_codes import ErrorCode
from ..exceptions import GateError
from ..gates import Gates
from ..models import AccessLink, CustomerUser
from ..protocols.customer import AuthCustomerInfo
from ..signals import access_link_created, customer_authenticated
from ._user_bridge import get_or_create_user_for_customer

if TYPE_CHECKING:
    from django.http import HttpRequest

    from ..senders import MessageSenderProtocol

logger = logging.getLogger("shopman.doorman.access_link")
User = get_user_model()


@dataclass
class TokenResult:
    """Result of token creation."""

    success: bool
    token: str | None = None
    url: str | None = None
    expires_at: str | None = None
    error: str | None = None
    error_code: ErrorCode | None = None


@dataclass
class AuthResult:
    """Result of token exchange."""

    success: bool
    user: User | None = None
    customer: AuthCustomerInfo | None = None
    created_user: bool = False
    error: str | None = None
    error_code: ErrorCode | None = None


@dataclass
class AccessLinkEmailResult:
    """Result of access link email request."""

    success: bool
    error: str | None = None
    error_code: ErrorCode | None = None


class AccessLinkService:
    """
    Access link authentication service.

    Creates tokens for chat-to-web authentication and email-based
    access links, and handles token exchange for Django session creation.
    """

    # ===========================================
    # Create Token
    # ===========================================

    @classmethod
    def create_token(
        cls,
        customer: AuthCustomerInfo,
        audience: str = AccessLink.Audience.WEB_GENERAL,
        source: str = AccessLink.Source.MANYCHAT,
        ttl_minutes: int | None = None,
        metadata: dict | None = None,
    ) -> TokenResult:
        """
        Create an AccessLink for Customer.

        Args:
            customer: Customer from Guestman
            audience: Token audience/scope
            source: Token source (manychat, api, internal)
            ttl_minutes: Time to live in minutes (default from settings)
            metadata: Additional metadata to store

        Returns:
            TokenResult with token and URL
        """
        ttl = ttl_minutes or doorman_settings.ACCESS_LINK_EXCHANGE_TTL_MINUTES
        expires_at = timezone.now() + timedelta(minutes=ttl)

        link, raw_token = AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=audience,
            source=source,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        url = cls._build_url(raw_token)

        # Signal
        access_link_created.send(
            sender=cls,
            token=link,
            customer=customer,
            audience=audience,
            source=source,
        )

        logger.info(
            "Access link created",
            extra={"customer_id": str(customer.uuid), "audience": audience},
        )

        return TokenResult(
            success=True,
            token=raw_token,
            url=url,
            expires_at=expires_at.isoformat(),
        )

    @classmethod
    def _build_url(cls, token: str) -> str:
        """Build the exchange URL for a token."""
        # Try to get domain from Sites framework
        try:
            from django.contrib.sites.models import Site

            domain = Site.objects.get_current().domain
        except Exception:
            domain = doorman_settings.DEFAULT_DOMAIN

        path = reverse("shopman_auth:access-exchange")
        protocol = "https" if doorman_settings.USE_HTTPS else "http"

        return f"{protocol}://{domain}{path}?t={token}"

    # ===========================================
    # Exchange
    # ===========================================

    @classmethod
    @transaction.atomic
    def exchange(
        cls,
        token_str: str,
        request: HttpRequest,
        required_audience: str | None = None,
        preserve_session_keys: list[str] | None = None,
    ) -> AuthResult:
        """
        Exchange token for Django session.

        Args:
            token_str: Token string
            request: Django HttpRequest
            required_audience: If set, token must have this audience
            preserve_session_keys: Session keys to preserve across login
                                   (e.g., ["basket_session_key"])

        Returns:
            AuthResult with user and customer
        """
        # Find token (lookup by HMAC hash, never plaintext)
        token = AccessLink.get_by_token(token_str)
        if token is None:
            logger.warning("Invalid token attempted")
            return AuthResult(success=False, error="Invalid token.", error_code=ErrorCode.TOKEN_INVALID)

        # G7: Validate
        try:
            Gates.access_link_validity(token, required_audience)
        except GateError as e:
            return AuthResult(success=False, error=e.message, error_code=ErrorCode.TOKEN_EXPIRED)

        # Fetch customer info via adapter
        adapter = get_adapter()
        customer = adapter.resolve_customer_by_uuid(token.customer_id)
        if not customer:
            return AuthResult(
                success=False, error="Customer not found.",
                error_code=ErrorCode.ACCOUNT_NOT_FOUND,
            )

        if not customer.is_active:
            return AuthResult(
                success=False, error="Account inactive.",
                error_code=ErrorCode.ACCOUNT_INACTIVE,
            )

        # Get or create User
        user, created_user = cls._get_or_create_user(customer)

        # Mark token as used
        token.mark_used(user)

        # Preserve session keys before login (login may rotate session)
        preserved = {}
        if preserve_session_keys:
            for key in preserve_session_keys:
                if key in request.session:
                    preserved[key] = request.session[key]
            # H04: Log only key names, never values (PII risk)
            logger.debug("Preserving session keys: %s", list(preserved.keys()))
        else:
            logger.debug("No session keys to preserve")

        # Django login
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        # Restore preserved session keys after login
        if preserved:
            for key, value in preserved.items():
                request.session[key] = value
            request.session.modified = True
            logger.debug("Restored %d session keys", len(preserved))
        else:
            logger.debug("No session keys to restore")

        # Signal
        customer_authenticated.send(
            sender=cls,
            customer=customer,
            user=user,
            method="access_link",
            request=request,
        )

        # Adapter hook
        adapter.on_customer_authenticated(request, customer, user, "access_link")

        logger.info(
            "Token exchanged",
            extra={
                "customer_id": str(customer.uuid),
                "user_id": user.id,
                "created_user": created_user,
            },
        )

        return AuthResult(
            success=True,
            user=user,
            customer=customer,
            created_user=created_user,
        )

    @classmethod
    def _get_or_create_user(cls, customer: AuthCustomerInfo) -> tuple[User, bool]:
        """Delegate to shared _user_bridge."""
        return get_or_create_user_for_customer(customer)

    # ===========================================
    # Access Link Email (email-based one-click login)
    # ===========================================

    @classmethod
    def send_access_link(
        cls,
        email: str,
        ip_address: str | None = None,
        sender: MessageSenderProtocol | None = None,
    ) -> AccessLinkEmailResult:
        """
        Send an access link to the given email address.

        Args:
            email: Customer email address.
            ip_address: Client IP for rate limiting.
            sender: Custom sender (default: EmailSender via Django templates).

        Returns:
            AccessLinkEmailResult with success status.
        """
        if not get_doorman_settings().ACCESS_LINK_ENABLED:
            return AccessLinkEmailResult(
                success=False, error="Access links are disabled.",
                error_code=ErrorCode.ACCESS_LINK_DISABLED,
            )

        email = email.strip().lower()
        if not email or "@" not in email:
            return AccessLinkEmailResult(
                success=False, error="Invalid email address.",
                error_code=ErrorCode.INVALID_EMAIL,
            )

        # G12: Rate limit by email
        settings = get_doorman_settings()
        try:
            Gates.access_link_rate_limit(
                email=email,
                max_requests=settings.ACCESS_LINK_RATE_LIMIT_MAX,
                window_minutes=settings.ACCESS_LINK_RATE_LIMIT_WINDOW_MINUTES,
            )
        except GateError:
            return AccessLinkEmailResult(
                success=False,
                error="Too many attempts. Please wait a few minutes.",
                error_code=ErrorCode.EMAIL_RATE_LIMIT,
            )

        # G10: Rate limit by IP (reuse existing gate)
        if ip_address:
            try:
                Gates.ip_rate_limit(ip_address)
            except GateError:
                return AccessLinkEmailResult(
                    success=False,
                    error="Too many attempts from this location.",
                    error_code=ErrorCode.IP_RATE_LIMIT,
                )

        # Find customer by email
        adapter = get_adapter()
        customer = adapter.resolve_customer_by_email(email)

        if not customer:
            if not adapter.should_auto_create_customer():
                return AccessLinkEmailResult(
                    success=False,
                    error="Account not found. Please contact support.",
                    error_code=ErrorCode.ACCOUNT_NOT_FOUND,
                )
            return AccessLinkEmailResult(
                success=False,
                error="Account not found for this email.",
                error_code=ErrorCode.ACCOUNT_NOT_FOUND,
            )

        if not customer.is_active:
            return AccessLinkEmailResult(
                success=False, error="Account inactive.",
                error_code=ErrorCode.ACCOUNT_INACTIVE,
            )

        # Create access link with email login TTL
        ttl = doorman_settings.ACCESS_LINK_TTL_MINUTES
        token_result = cls.create_token(
            customer=customer,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            ttl_minutes=ttl,
            metadata={"method": "access_link", "email": email},
        )

        if not token_result.success:
            return AccessLinkEmailResult(
                success=False, error="Failed to create login link.",
                error_code=ErrorCode.SEND_FAILED,
            )

        # Send email with the access link URL
        sent = cls._send_access_link_email(email, token_result.url, ttl, sender)
        if not sent:
            return AccessLinkEmailResult(
                success=False, error="Failed to send email.",
                error_code=ErrorCode.SEND_FAILED,
            )

        logger.info(
            "Access link sent",
            extra={"email": email, "customer_id": str(customer.uuid)},
        )

        return AccessLinkEmailResult(success=True)

    @classmethod
    def _send_access_link_email(
        cls,
        email: str,
        url: str,
        ttl_minutes: int,
        sender: MessageSenderProtocol | None = None,
    ) -> bool:
        """Send the access link email using Django templates."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.translation import gettext as _

        context = {"url": url, "ttl_minutes": ttl_minutes, "email": email}

        try:
            subject = _("Your login link")
            text_body = render_to_string(
                doorman_settings.TEMPLATE_ACCESS_LINK_EMAIL_TXT, context
            )
            html_body = render_to_string(
                doorman_settings.TEMPLATE_ACCESS_LINK_EMAIL_HTML, context
            )

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=None,  # DEFAULT_FROM_EMAIL
                to=[email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)

            logger.info("Access link email sent", extra={"email": email})
            return True
        except Exception:
            logger.exception("Access link email send failed", extra={"email": email})
            return False

    # ===========================================
    # Create and Send (unified channel delivery)
    # ===========================================

    @classmethod
    def create_and_send(
        cls,
        customer: AuthCustomerInfo,
        channel: str = "email",
        audience: str = AccessLink.Audience.WEB_GENERAL,
        ttl_minutes: int | None = None,
    ) -> AccessLinkEmailResult:
        """
        Create an access link and send it via the specified channel.

        Unified method that covers email, whatsapp, sms, and api delivery.
        Internally creates AccessLink + builds URL + calls adapter.send_access_link().

        Args:
            customer: Target customer.
            channel: Delivery channel (email, whatsapp, sms, api).
            audience: Token audience.
            ttl_minutes: TTL override.

        Returns:
            AccessLinkEmailResult with success status.
        """
        ttl = ttl_minutes or doorman_settings.ACCESS_LINK_TTL_MINUTES
        token_result = cls.create_token(
            customer=customer,
            audience=audience,
            source=AccessLink.Source.INTERNAL,
            ttl_minutes=ttl,
            metadata={"method": "access_link", "channel": channel},
        )

        if not token_result.success:
            return AccessLinkEmailResult(success=False, error="Failed to create login link.")

        adapter = get_adapter()
        sent = adapter.send_access_link(channel, customer, token_result.url)
        if not sent:
            return AccessLinkEmailResult(success=False, error=f"Failed to send via {channel}.")

        logger.info(
            "Access link sent via %s",
            channel,
            extra={"customer_id": str(customer.uuid), "channel": channel},
        )

        return AccessLinkEmailResult(success=True)

    # ===========================================
    # Utilities
    # ===========================================

    @classmethod
    def get_customer_for_user(cls, user) -> AuthCustomerInfo | None:
        """
        Get Customer for a Django User.

        Args:
            user: Django User instance

        Returns:
            AuthCustomerInfo or None
        """
        try:
            link = CustomerUser.objects.get(user=user)
            adapter = get_adapter()
            return adapter.resolve_customer_by_uuid(link.customer_id)
        except CustomerUser.DoesNotExist:
            return None

    @classmethod
    def get_user_for_customer(cls, customer: AuthCustomerInfo) -> User | None:
        """
        Get Django User for a Customer.

        Args:
            customer: Customer from Guestman

        Returns:
            User or None
        """
        try:
            link = CustomerUser.objects.select_related("user").get(
                customer_id=customer.uuid,
            )
            return link.user
        except CustomerUser.DoesNotExist:
            return None

    @classmethod
    def cleanup_expired_tokens(cls, days: int = 7) -> int:
        """
        Delete expired tokens older than N days.

        Args:
            days: Delete tokens older than this many days

        Returns:
            Number of deleted tokens
        """
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = AccessLink.objects.filter(
            expires_at__lt=cutoff,
        ).delete()
        return deleted
