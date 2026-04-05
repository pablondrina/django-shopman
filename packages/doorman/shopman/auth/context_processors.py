"""
Auth context processors — inject customer into template context.
"""
from __future__ import annotations


def customer(request):
    """Add `auth_customer` to template context from request.customer."""
    return {
        "auth_customer": getattr(request, "customer", None),
    }
