"""
Shopman Attending — Customer Management.

Usage:
    from shopman.attending.services.customer import get, validate, get_listing_code
    from shopman.attending.gates import Gates, GateError, GateResult

    cust = get("CUST-001")
    validation = validate("CUST-001")
    listing = get_listing_code("CUST-001")

    # Gates validation
    Gates.contact_point_uniqueness("whatsapp", "+5543999999999")
    Gates.provider_event_authenticity(body, signature, secret)
"""

__title__ = "Shopman Attending"
__version__ = "0.1.0"
__author__ = "Pablo Valentini"


def __getattr__(name):
    if name == "Gates":
        from shopman.attending.gates import Gates

        return Gates
    if name == "GateError":
        from shopman.attending.gates import GateError

        return GateError
    if name == "GateResult":
        from shopman.attending.gates import GateResult

        return GateResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Gates", "GateError", "GateResult"]
