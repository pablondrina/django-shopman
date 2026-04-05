"""Customers services (CORE only).

CORE services are exported here. Contrib services are in their respective modules:
- shopman.customers.contrib.preferences: PreferenceService
- shopman.customers.contrib.insights: InsightService
- shopman.customers.contrib.identifiers: IdentifierService
"""

from shopman.customers.services import customer
from shopman.customers.services import address

__all__ = ["customer", "address"]
