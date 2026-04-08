"""
Customers Identifiers - Multi-channel customer deduplication.

This contrib module provides CustomerIdentifier for linking multiple
channel identities (WhatsApp, Instagram, Facebook, etc.) to a single customer.

Usage:
    INSTALLED_APPS = [
        ...
        "customers",
        guestman.contrib.identifiers",
    ]

    from shopman.guestman.contrib.identifiers import IdentifierService

    customer = IdentifierService.find_by_identifier("whatsapp", "5511999999999")
    IdentifierService.add_identifier(customer_ref, "instagram", "username")
"""


def __getattr__(name):
    if name == "IdentifierService":
        from shopman.guestman.contrib.identifiers.service import IdentifierService

        return IdentifierService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["IdentifierService"]
