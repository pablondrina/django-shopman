"""
MagicLinkService — Email-based one-click passwordless login.

Flow:
1. Customer enters email on the magic link form.
2. We find/create the Customer via resolver.
3. Create a BridgeToken with longer TTL (15 min default).
4. Send the exchange URL via email.
5. Customer clicks link → standard bridge exchange → session.

This reuses BridgeToken infrastructure entirely. No new models needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..conf import auth_settings, get_customer_resolver, get_auth_settings
from ..exceptions import GateError
from ..gates import Gates
from ..models import BridgeToken
from ..services.auth_bridge import AuthBridgeService

if TYPE_CHECKING:
    from ..senders import MessageSenderProtocol

logger = logging.getLogger("shopman.auth.magic_link")


@dataclass
class MagicLinkResult:
    """Result of magic link request."""

    success: bool
    error: str | None = None


class MagicLinkService:
    """
    Magic link service — sends a one-click login URL via email.

    Perfect for e-commerce checkout flows where the customer
    has an email but no phone / WhatsApp.
    """

    @classmethod
    def send_magic_link(
        cls,
        email: str,
        ip_address: str | None = None,
        sender: "MessageSenderProtocol | None" = None,
    ) -> MagicLinkResult:
        """
        Send a magic link to the given email address.

        Args:
            email: Customer email address.
            ip_address: Client IP for rate limiting.
            sender: Custom sender (default: EmailSender via Django templates).

        Returns:
            MagicLinkResult with success status.
        """
        if not get_auth_settings().MAGIC_LINK_ENABLED:
            return MagicLinkResult(success=False, error="Magic links are disabled.")

        email = email.strip().lower()
        if not email or "@" not in email:
            return MagicLinkResult(success=False, error="Invalid email address.")

        # G12: Rate limit by email
        settings = get_auth_settings()
        try:
            Gates.magic_link_rate_limit(
                email=email,
                max_requests=settings.MAGIC_LINK_RATE_LIMIT_MAX,
                window_minutes=settings.MAGIC_LINK_RATE_LIMIT_WINDOW_MINUTES,
            )
        except GateError:
            return MagicLinkResult(
                success=False,
                error="Too many attempts. Please wait a few minutes.",
            )

        # G10: Rate limit by IP (reuse existing gate)
        if ip_address:
            try:
                Gates.ip_rate_limit(ip_address)
            except GateError:
                return MagicLinkResult(
                    success=False,
                    error="Too many attempts from this location.",
                )

        # Find customer by email
        resolver = get_customer_resolver()
        customer = resolver.get_by_email(email)

        if not customer:
            if not get_auth_settings().AUTO_CREATE_CUSTOMER:
                return MagicLinkResult(
                    success=False,
                    error="Account not found. Please contact support.",
                )
            # For magic link, we need to find by email specifically
            # If the resolver doesn't find by email, we can't create without phone
            return MagicLinkResult(
                success=False,
                error="Account not found for this email.",
            )

        if not customer.is_active:
            return MagicLinkResult(success=False, error="Account inactive.")

        # Create bridge token with magic link TTL
        ttl = auth_settings.MAGIC_LINK_TTL_MINUTES
        token_result = AuthBridgeService.create_token(
            customer=customer,
            audience=BridgeToken.Audience.WEB_GENERAL,
            source=BridgeToken.Source.INTERNAL,
            ttl_minutes=ttl,
            metadata={"method": "magic_link", "email": email},
        )

        if not token_result.success:
            return MagicLinkResult(success=False, error="Failed to create login link.")

        # Send email with the magic link URL
        sent = cls._send_magic_link_email(email, token_result.url, ttl, sender)
        if not sent:
            return MagicLinkResult(success=False, error="Failed to send email.")

        logger.info(
            "Magic link sent",
            extra={"email": email, "customer_id": str(customer.uuid)},
        )

        return MagicLinkResult(success=True)

    @classmethod
    def _send_magic_link_email(
        cls,
        email: str,
        url: str,
        ttl_minutes: int,
        sender: "MessageSenderProtocol | None" = None,
    ) -> bool:
        """Send the magic link email using Django templates."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.translation import gettext as _

        context = {"url": url, "ttl_minutes": ttl_minutes, "email": email}

        try:
            subject = _("Your login link")
            text_body = render_to_string(
                auth_settings.TEMPLATE_MAGIC_LINK_EMAIL_TXT, context
            )
            html_body = render_to_string(
                auth_settings.TEMPLATE_MAGIC_LINK_EMAIL_HTML, context
            )

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=None,  # DEFAULT_FROM_EMAIL
                to=[email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)

            logger.info("Magic link email sent", extra={"email": email})
            return True
        except Exception:
            logger.exception("Magic link email send failed", extra={"email": email})
            return False
