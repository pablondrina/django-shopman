"""
Shopman Customers — Customer Management.

Usage:
    from shopman.customers.services.customer import get, validate, get_listing_ref
    from shopman.customers.gates import Gates, GateError, GateResult

    cust = get("CUST-001")
    validation = validate("CUST-001")
    listing = get_listing_ref("CUST-001")

    # Gates validation
    Gates.contact_point_uniqueness("whatsapp", "+5543999999999")
    Gates.provider_event_authenticity(body, signature, secret)
"""

__title__ = "Shopman Customers"
__version__ = "0.1.0"
__author__ = "Pablo Valentini"


def __getattr__(name):
    if name == "Gates":
        from shopman.customers.gates import Gates

        return Gates
    if name == "GateError":
        from shopman.customers.gates import GateError

        return GateError
    if name == "GateResult":
        from shopman.customers.gates import GateResult

        return GateResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Gates", "GateError", "GateResult"]
