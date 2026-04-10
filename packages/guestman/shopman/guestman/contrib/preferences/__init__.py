"""
Guestman Preferences - Customer preferences management.

This contrib module provides CustomerPreference for storing explicit,
inferred, and restriction preferences.

Usage:
    INSTALLED_APPS = [
        ...
        "customers",
        guestman.contrib.preferences",
    ]

    from shopman.guestman.contrib.preferences import PreferenceService

    PreferenceService.set_preference(customer_ref, "dietary", "lactose_free", True)
    value = PreferenceService.get_preference(customer_ref, "dietary", "lactose_free")
"""


def __getattr__(name):
    if name == "PreferenceService":
        from shopman.guestman.contrib.preferences.service import PreferenceService

        return PreferenceService
    if name in ("CustomerPreference", "PreferenceType"):
        from shopman.guestman.contrib.preferences import models

        return getattr(models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["PreferenceService", "CustomerPreference", "PreferenceType"]
