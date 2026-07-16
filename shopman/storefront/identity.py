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


def customer_pricing_hints(request) -> tuple[str, str]:
    """Return ``(customer_group, customer_segment)`` for the authenticated viewer.

    Feeds the pricing context so a promotion gated by ``customer_segments``
    (loyalty group or RFM segment) shows on the menu/PDP for an eligible member —
    the same two axes ``DiscountModifier._matches`` checks in the cart. Returns
    ``("", "")`` for an anonymous viewer or on any lookup failure (open to all).
    """
    import logging

    from django.core.exceptions import ObjectDoesNotExist

    logger = logging.getLogger(__name__)
    if request is None:
        return "", ""
    try:
        customer = get_authenticated_customer(request)
        if customer is None:
            return "", ""
        group = customer.group.ref if getattr(customer, "group_id", None) else ""
        try:
            segment = customer.insight.rfm_segment or ""
        except ObjectDoesNotExist:
            segment = ""  # insight (OneToOne) not computed yet — match by group only
        return group, segment
    except Exception:
        logger.warning("customer_pricing_hints failed", exc_info=True)
        return "", ""
