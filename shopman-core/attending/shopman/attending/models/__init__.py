"""Attending models (CORE only).

CORE models are exported here. Contrib models are in their respective modules:
- guestman.contrib.identifiers: CustomerIdentifier, IdentifierType
- guestman.contrib.preferences: CustomerPreference, PreferenceType
- guestman.contrib.insights: CustomerInsight
"""

from shopman.attending.models.group import CustomerGroup
from shopman.attending.models.customer import Customer, CustomerType
from shopman.attending.models.address import CustomerAddress, AddressLabel
from shopman.attending.models.contact_point import ContactPoint
from shopman.attending.models.external_identity import ExternalIdentity
from shopman.attending.models.processed_event import ProcessedEvent

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
