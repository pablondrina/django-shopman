"""
Attending Consent - LGPD-compliant communication opt-in/opt-out.

Tracks per-channel consent for customer communications (WhatsApp, email, SMS, push).
Required for LGPD/GDPR compliance — never send marketing without active consent.

Usage:
    INSTALLED_APPS = [
        ...
        "attending",
        "attending.contrib.consent",
    ]

    from shopman.attending.contrib.consent import ConsentService

    ConsentService.grant_consent("CUST-001", "whatsapp", source="checkout_form")
    can_send = ConsentService.has_consent("CUST-001", "whatsapp")
    ConsentService.revoke_consent("CUST-001", "whatsapp")
"""


def __getattr__(name):
    if name == "ConsentService":
        from shopman.attending.contrib.consent.service import ConsentService

        return ConsentService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ConsentService"]
