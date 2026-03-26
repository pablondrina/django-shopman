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

from ..conf import auth_settings, get_customer_resolver, get_auth_settings
from ..protocols.customer import AuthCustomerInfo
from ..exceptions import GateError
from ..gates import Gates
from ..models import AccessLink, CustomerUser
from ..signals import access_link_created, customer_authenticated

if TYPE_CHECKING:
    from django.http import HttpRequest

    from ..senders import MessageSenderProtocol

logger = logging.getLogger("shopman.auth.access_link")
User = get_user_model()


@dataclass
class TokenResult:
    """Result of token creation."""

    success: bool
    token: str | None = None
    url: str | None = None
    expires_at: str | None = None
    error: str | None = None


@dataclass
class AuthResult:
    """Result of token exchange."""

    success: bool
    user: User | None = None
    customer: AuthCustomerInfo | None = None
    created_user: bool = False
    error: str | None = None


@dataclass
class AccessLinkEmailResult:
    """Result of access link email request."""

    success: bool
    error: str | None = None


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
            customer: Customer from Customers
            audience: Token audience/scope
            source: Token source (manychat, api, internal)
            ttl_minutes: Time to live in minutes (default from settings)
            metadata: Additional metadata to store

        Returns:
            TokenResult with token and URL
        """
        ttl = ttl_minutes or auth_settings.BRIDGE_TOKEN_TTL_MINUTES
        expires_at = timezone.now() + timedelta(minutes=ttl)

        token = AccessLink.objects.create(
            customer_id=customer.uuid,
            audience=audience,
            source=source,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        url = cls._build_url(token.token)

        # Signal
        access_link_created.send(
            sender=cls,
            token=token,
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
            token=token.token,
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
            domain = auth_settings.DEFAULT_DOMAIN

        path = reverse("shopman_auth:bridge-exchange")
        protocol = "https" if auth_settings.USE_HTTPS else "http"

        return f"{protocol}://{domain}{path}?t={token}"

    # ===========================================
    # Exchange
    # ===========================================

    @classmethod
    @transaction.atomic
    def exchange(
        cls,
        token_str: str,
        request: "HttpRequest",
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
        # Find token
        try:
            token = AccessLink.objects.get(token=token_str)
        except AccessLink.DoesNotExist:
            logger.warning("Invalid token", extra={"token": token_str[:8]})
            return AuthResult(success=False, error="Invalid token.")

        # G7: Validate
        try:
            Gates.access_link_validity(token, required_audience)
        except GateError as e:
            return AuthResult(success=False, error=e.message)

        # Fetch customer info via resolver
        resolver = get_customer_resolver()
        customer = resolver.get_by_uuid(token.customer_id)
        if not customer:
            return AuthResult(success=False, error="Customer not found.")

        if not customer.is_active:
            return AuthResult(success=False, error="Account inactive.")

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
        """
        Get or create User for Customer.

        Handles concurrent creation via IntegrityError retry.

        Args:
            customer: Customer from Customers

        Returns:
            (User, created) tuple
        """
        from django.db import IntegrityError

        # Check existing link
        try:
            link = CustomerUser.objects.select_related("user").get(
                customer_id=customer.uuid,
            )
            return link.user, False
        except CustomerUser.DoesNotExist:
            pass

        # Create User
        username = f"customer_{str(customer.uuid).replace('-', '')[:12]}"
        user = User.objects.create_user(username=username)

        # Set name from customer
        if customer.name:
            parts = customer.name.split(" ", 1)
            user.first_name = parts[0]
            if len(parts) > 1:
                user.last_name = parts[1]
            user.save(update_fields=["first_name", "last_name"])

        # Create link — retry on concurrent creation
        try:
            CustomerUser.objects.create(user=user, customer_id=customer.uuid)
        except IntegrityError:
            # Another request already created the link; use that one
            user.delete()
            link = CustomerUser.objects.select_related("user").get(
                customer_id=customer.uuid,
            )
            return link.user, False

        logger.info(
            "User created for customer",
            extra={"customer_id": str(customer.uuid), "user_id": user.id},
        )

        return user, True

    # ===========================================
    # Access Link Email (email-based one-click login)
    # ===========================================

    @classmethod
    def send_access_link(
        cls,
        email: str,
        ip_address: str | None = None,
        sender: "MessageSenderProtocol | None" = None,
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
        if not get_auth_settings().ACCESS_LINK_ENABLED:
            return AccessLinkEmailResult(success=False, error="Access links are disabled.")

        email = email.strip().lower()
        if not email or "@" not in email:
            return AccessLinkEmailResult(success=False, error="Invalid email address.")

        # G12: Rate limit by email
        settings = get_auth_settings()
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
            )

        # G10: Rate limit by IP (reuse existing gate)
        if ip_address:
            try:
                Gates.ip_rate_limit(ip_address)
            except GateError:
                return AccessLinkEmailResult(
                    success=False,
                    error="Too many attempts from this location.",
                )

        # Find customer by email
        resolver = get_customer_resolver()
        customer = resolver.get_by_email(email)

        if not customer:
            if not get_auth_settings().AUTO_CREATE_CUSTOMER:
                return AccessLinkEmailResult(
                    success=False,
                    error="Account not found. Please contact support.",
                )
            return AccessLinkEmailResult(
                success=False,
                error="Account not found for this email.",
            )

        if not customer.is_active:
            return AccessLinkEmailResult(success=False, error="Account inactive.")

        # Create access link with email login TTL
        ttl = auth_settings.ACCESS_LINK_TTL_MINUTES
        token_result = cls.create_token(
            customer=customer,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            ttl_minutes=ttl,
            metadata={"method": "access_link", "email": email},
        )

        if not token_result.success:
            return AccessLinkEmailResult(success=False, error="Failed to create login link.")

        # Send email with the access link URL
        sent = cls._send_access_link_email(email, token_result.url, ttl, sender)
        if not sent:
            return AccessLinkEmailResult(success=False, error="Failed to send email.")

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
        sender: "MessageSenderProtocol | None" = None,
    ) -> bool:
        """Send the access link email using Django templates."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.translation import gettext as _

        context = {"url": url, "ttl_minutes": ttl_minutes, "email": email}

        try:
            subject = _("Your login link")
            text_body = render_to_string(
                auth_settings.TEMPLATE_ACCESS_LINK_EMAIL_TXT, context
            )
            html_body = render_to_string(
                auth_settings.TEMPLATE_ACCESS_LINK_EMAIL_HTML, context
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
            resolver = get_customer_resolver()
            return resolver.get_by_uuid(link.customer_id)
        except CustomerUser.DoesNotExist:
            return None

    @classmethod
    def get_user_for_customer(cls, customer: AuthCustomerInfo) -> User | None:
        """
        Get Django User for a Customer.

        Args:
            customer: Customer from Customers

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
