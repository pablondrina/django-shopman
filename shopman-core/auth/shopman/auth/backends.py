"""
Django authentication backend for phone OTP login.

Integrates shopman.auth with Django's auth framework so that
``request.user`` and ``@login_required`` work for OTP-verified customers.

Usage in settings.py::

    AUTHENTICATION_BACKENDS = [
        "shopman.auth.backends.PhoneOTPBackend",
        "django.contrib.auth.backends.ModelBackend",
    ]
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from .services._user_bridge import get_or_create_user_for_customer

logger = logging.getLogger("shopman.auth.backends")
User = get_user_model()


class PhoneOTPBackend(BaseBackend):
    """
    Authenticate a customer by their UUID after OTP verification.

    This backend is called by ``django.contrib.auth.authenticate()``
    with ``customer_id=<uuid>`` after the OTP code has been verified
    by AuthService. It resolves the customer to a Django User via
    CustomerUser and returns it.
    """

    def authenticate(self, request, customer_id=None, **kwargs: Any):
        """
        Authenticate by customer UUID.

        Args:
            request: Django HttpRequest.
            customer_id: Customer UUID (verified by AuthService).

        Returns:
            User instance or None.
        """
        if customer_id is None:
            return None

        from .conf import get_customer_resolver

        resolver = get_customer_resolver()
        customer = resolver.get_by_uuid(customer_id)

        if customer is None:
            logger.warning(
                "Backend: customer not found",
                extra={"customer_id": str(customer_id)},
            )
            return None

        if not customer.is_active:
            logger.warning(
                "Backend: customer inactive",
                extra={"customer_id": str(customer_id)},
            )
            return None

        user, created = get_or_create_user_for_customer(customer)

        if created:
            logger.info(
                "Backend: user created for customer",
                extra={"customer_id": str(customer_id), "user_id": user.id},
            )

        return user

    def get_user(self, user_id: int):
        """Standard Django user lookup."""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
