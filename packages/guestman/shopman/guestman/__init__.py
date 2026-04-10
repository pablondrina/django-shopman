"""
Shopman Guestman — Customer Management.

Usage:
    from shopman.guestman.services.customer import get, validate, get_listing_ref
    from shopman.guestman.gates import Gates, GateError, GateResult

    cust = get("CUST-001")
    validation = validate("CUST-001")
    listing = get_listing_ref("CUST-001")

    # Gates validation
    Gates.contact_point_uniqueness("whatsapp", "+5543999999999")
    Gates.provider_event_authenticity(body, signature, secret)

Contribs (public API):
    from shopman.guestman.contrib.preferences import PreferenceService
    from shopman.guestman.contrib.identifiers import IdentifierService
    from shopman.guestman.contrib.loyalty import LoyaltyService
    from shopman.guestman.contrib.timeline import TimelineService
    from shopman.guestman.contrib.insights import InsightService
    from shopman.guestman.contrib.consent import ConsentService
"""

__title__ = "Shopman Guestman"
__version__ = "0.1.0"
__author__ = "Pablo Valentini"

_GATES_NAMES = {"Gates", "GateError", "GateResult"}

_CONTRIB_MAP = {
    "PreferenceService": "shopman.guestman.contrib.preferences",
    "CustomerPreference": "shopman.guestman.contrib.preferences",
    "PreferenceType": "shopman.guestman.contrib.preferences",
    "IdentifierService": "shopman.guestman.contrib.identifiers",
    "CustomerIdentifier": "shopman.guestman.contrib.identifiers",
    "IdentifierType": "shopman.guestman.contrib.identifiers",
    "LoyaltyService": "shopman.guestman.contrib.loyalty",
    "LoyaltyAccount": "shopman.guestman.contrib.loyalty",
    "LoyaltyTransaction": "shopman.guestman.contrib.loyalty",
    "LoyaltyTier": "shopman.guestman.contrib.loyalty",
    "TimelineService": "shopman.guestman.contrib.timeline",
    "TimelineEvent": "shopman.guestman.contrib.timeline",
    "EventType": "shopman.guestman.contrib.timeline",
    "InsightService": "shopman.guestman.contrib.insights",
    "CustomerInsight": "shopman.guestman.contrib.insights",
    "ConsentService": "shopman.guestman.contrib.consent",
    "CommunicationConsent": "shopman.guestman.contrib.consent",
}


def __getattr__(name):
    if name in _GATES_NAMES:
        import importlib

        mod = importlib.import_module("shopman.guestman.gates")
        return getattr(mod, name)
    if name in _CONTRIB_MAP:
        import importlib

        mod = importlib.import_module(_CONTRIB_MAP[name])
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Gates",
    "GateError",
    "GateResult",
    *_CONTRIB_MAP,
]
