"""Attending services (CORE only).

CORE services are exported here. Contrib services are in their respective modules:
- guestman.contrib.preferences: PreferenceService
- guestman.contrib.insights: InsightService
- guestman.contrib.identifiers: IdentifierService
"""

from shopman.attending.services import customer
from shopman.attending.services import address

__all__ = ["customer", "address"]
