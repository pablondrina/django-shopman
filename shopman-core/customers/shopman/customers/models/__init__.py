"""Customers models (CORE only).

CORE models are exported here. Contrib models are in their respective modules:
- shopman.customers.contrib.identifiers: CustomerIdentifier, IdentifierType
- shopman.customers.contrib.preferences: CustomerPreference, PreferenceType
- shopman.customers.contrib.insights: CustomerInsight
"""

from shopman.customers.models.group import CustomerGroup
from shopman.customers.models.customer import Customer, CustomerType
from shopman.customers.models.address import CustomerAddress, AddressLabel
from shopman.customers.models.contact_point import ContactPoint
from shopman.customers.models.external_identity import ExternalIdentity
from shopman.customers.models.processed_event import ProcessedEvent

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
