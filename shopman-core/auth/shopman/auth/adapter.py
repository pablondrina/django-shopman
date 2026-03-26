"""
DefaultAuthAdapter — single point of customization for auth behavior.

Inspired by django-allauth's DefaultAccountAdapter. Provides hooks for
customer resolution, code delivery, login events, and redirects.

The default implementation delegates to the existing CustomerResolver
and MessageSender protocols for backward compatibility.

Usage::

    # settings.py
    AUTH = {
        "AUTH_ADAPTER": "myapp.auth.MyAuthAdapter",
    }

    # myapp/auth.py
    from shopman.auth.adapter import DefaultAuthAdapter

    class MyAuthAdapter(DefaultAuthAdapter):
        def on_customer_authenticated(self, request, customer, user, method):
            analytics.track("login", customer_id=str(customer.uuid))
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .conf import auth_settings, get_customer_resolver
from .protocols.customer import AuthCustomerInfo
from .utils import normalize_phone

if TYPE_CHECKING:
    from django.http import HttpRequest

    from .models.device_trust import TrustedDevice

logger = logging.getLogger("shopman.auth.adapter")


class DefaultAuthAdapter:
    """
    Default auth adapter.

    Delegates to CustomerResolver and MessageSender from settings.
    Override methods in a subclass for custom behavior.
    """

    def __init__(self):
        self._resolver = None
        self._sender = None

    # ===========================================
    # Customer resolution
    # ===========================================

    @property
    def resolver(self):
        if self._resolver is None:
            self._resolver = get_customer_resolver()
        return self._resolver

    def resolve_customer_by_phone(self, phone: str) -> AuthCustomerInfo | None:
        """Resolve customer by phone number."""
        return self.resolver.get_by_phone(phone)

    def resolve_customer_by_email(self, email: str) -> AuthCustomerInfo | None:
        """Resolve customer by email address."""
        return self.resolver.get_by_email(email)

    def resolve_customer_by_uuid(self, uuid) -> AuthCustomerInfo | None:
        """Resolve customer by UUID."""
        return self.resolver.get_by_uuid(uuid)

    def create_customer_for_phone(self, phone: str) -> AuthCustomerInfo:
        """Create a new customer for the given phone number."""
        return self.resolver.create_for_phone(phone)

    # ===========================================
    # Code delivery
    # ===========================================

    @property
    def sender(self):
        if self._sender is None:
            from django.utils.module_loading import import_string

            sender_class = import_string(auth_settings.MESSAGE_SENDER_CLASS)
            self._sender = sender_class()
        return self._sender

    def send_code(self, target: str, code: str, method: str) -> bool:
        """
        Send a verification code.

        Args:
            target: Phone (E.164) or email.
            code: The raw OTP code.
            method: Delivery method (whatsapp, sms, email).

        Returns:
            True if sent successfully.
        """
        return self.sender.send_code(target, code, method)

    def send_access_link(self, channel: str, customer: AuthCustomerInfo, url: str) -> bool:
        """
        Send an access link via the specified channel.

        Args:
            channel: Delivery channel (email, whatsapp, sms, api).
            customer: The target customer.
            url: The access link URL.

        Returns:
            True if sent successfully.
        """
        if channel == "email":
            return self._send_access_link_email(customer, url)
        elif channel == "api":
            # API channel: the caller handles delivery
            return True
        else:
            # For whatsapp/sms: send the URL as a code/message
            target = customer.phone or ""
            return self.sender.send_code(target, url, channel)

    def _send_access_link_email(self, customer: AuthCustomerInfo, url: str) -> bool:
        """Send access link via email."""
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.translation import gettext as _

        email = customer.email
        if not email:
            logger.warning("No email for customer %s", customer.uuid)
            return False

        ttl = auth_settings.ACCESS_LINK_TTL_MINUTES
        context = {"url": url, "ttl_minutes": ttl, "email": email}

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
                from_email=None,
                to=[email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)

            logger.info("Access link email sent", extra={"email": email})
            return True
        except Exception:
            logger.exception("Access link email send failed", extra={"email": email})
            return False

    def get_delivery_chain(self, target: str) -> list[str]:
        """
        Get the delivery chain for a target.

        Default: single method from settings. AUTH-3 will add fallback chain.
        """
        return ["whatsapp"]

    # ===========================================
    # Lifecycle hooks
    # ===========================================

    def on_customer_authenticated(
        self,
        request: "HttpRequest",
        customer: AuthCustomerInfo,
        user,
        method: str,
    ) -> None:
        """
        Called after successful authentication.

        Override for custom post-auth logic (analytics, sync, etc.).
        Signals still fire independently.

        Args:
            request: Django request.
            customer: Authenticated customer.
            user: Django User.
            method: Auth method (access_link, verification_code).
        """
        pass

    def on_device_trusted(
        self,
        request: "HttpRequest",
        customer: AuthCustomerInfo,
        device: "TrustedDevice",
    ) -> None:
        """Called after a device is marked as trusted."""
        pass

    def on_login_failed(
        self,
        request: "HttpRequest | None",
        target: str,
        reason: str,
    ) -> None:
        """Called when a login attempt fails."""
        pass

    # ===========================================
    # Configuration
    # ===========================================

    def should_auto_create_customer(self) -> bool:
        """Whether to auto-create customers on first login."""
        return auth_settings.AUTO_CREATE_CUSTOMER

    def normalize_phone(self, raw: str) -> str:
        """Normalize a phone number to E.164."""
        return normalize_phone(raw)

    def is_login_allowed(self, target: str, method: str) -> bool:
        """
        Whether login is allowed for this target/method.

        Override to block specific targets or methods.
        """
        return True

    # ===========================================
    # Redirects
    # ===========================================

    def get_login_redirect_url(self, request: "HttpRequest", customer: AuthCustomerInfo) -> str:
        """Get the URL to redirect to after login."""
        return auth_settings.LOGIN_REDIRECT_URL

    def get_logout_redirect_url(self, request: "HttpRequest") -> str:
        """Get the URL to redirect to after logout."""
        return auth_settings.LOGOUT_REDIRECT_URL
