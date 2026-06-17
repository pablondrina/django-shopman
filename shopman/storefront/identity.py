"""Customer identity resolution for the storefront API surface.

Headless: the customer-facing pages live in the Nuxt store; the Django
storefront is the API the BFF consumes. This helper resolves the authenticated
customer from the request (``request.customer`` is set by the doorman auth
middleware) for the API views.
"""

from __future__ import annotations

from shopman.shop.services import auth as auth_service


def get_authenticated_customer(request):
    """Return the Customer model for an authenticated request, or None.

    Reads ``request.customer`` (set by AuthCustomerMiddleware) and resolves the
    full Customer model via the auth service.
    """
    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return None
    return auth_service.customer_by_uuid(customer_info.uuid)
