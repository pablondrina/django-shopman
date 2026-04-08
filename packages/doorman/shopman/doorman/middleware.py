"""
Auth middleware — resolves request.customer from request.user.

After Django's AuthenticationMiddleware sets request.user, this middleware
resolves the linked Customer via CustomerUser and the adapter, setting
request.customer = AuthCustomerInfo | None.

The result is cached on the user instance to avoid repeated queries.
"""
from __future__ import annotations

import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("shopman.doorman.middleware")

_CACHE_ATTR = "_shopman_customer_info"


class AuthCustomerMiddleware(MiddlewareMixin):
    """Resolve customer from authenticated user, set request.customer."""

    def process_request(self, request):
        request.customer = self._resolve_customer(request)

    def _resolve_customer(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        # Check cache on user instance (1 query per request)
        cached = getattr(user, _CACHE_ATTR, None)
        if cached is not None:
            return cached

        try:
            from .models import CustomerUser

            link = CustomerUser.objects.filter(user=user).select_related().first()
            if link is None:
                setattr(user, _CACHE_ATTR, None)
                return None

            from .conf import get_adapter

            adapter = get_adapter()
            customer_info = adapter.resolve_customer_by_uuid(link.customer_id)
            setattr(user, _CACHE_ATTR, customer_info)
            return customer_info
        except Exception:
            logger.exception("Failed to resolve customer for user %s", user.pk)
            return None
