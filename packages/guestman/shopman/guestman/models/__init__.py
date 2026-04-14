"""Guestman models (CORE only).

CORE models are exported here. Contrib models are in their respective modules:
- shopman.guestman.contrib.identifiers: CustomerIdentifier, IdentifierType
- shopman.guestman.contrib.preferences: CustomerPreference, PreferenceType
- shopman.guestman.contrib.insights: CustomerInsight
"""

from shopman.guestman.models.address import AddressLabel, CustomerAddress
from shopman.guestman.models.contact_point import ContactPoint
from shopman.guestman.models.customer import Customer, CustomerType
from shopman.guestman.models.external_identity import ExternalIdentity
from shopman.guestman.models.group import CustomerGroup
from shopman.guestman.models.processed_event import ProcessedEvent

__all__ = [
    # Core models
    "CustomerGroup",
    "Customer",
    "CustomerType",
    "CustomerAddress",
    "AddressLabel",
    # Multi-channel contact management
    "ContactPoint",
    "ExternalIdentity",
    # Replay protection (G5)
    "ProcessedEvent",
]
