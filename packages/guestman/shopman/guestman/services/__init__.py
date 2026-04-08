"""Customers services (CORE only).

CORE services are exported here. Contrib services are in their respective modules:
- shopman.guestman.contrib.preferences: PreferenceService
- shopman.guestman.contrib.insights: InsightService
- shopman.guestman.contrib.identifiers: IdentifierService
"""

from shopman.guestman.services import customer
from shopman.guestman.services import address

__all__ = ["customer", "address"]
