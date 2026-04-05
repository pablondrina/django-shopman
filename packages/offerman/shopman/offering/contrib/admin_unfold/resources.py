"""Re-export resources from shopman.offering.contrib.import_export for backwards compatibility."""
from __future__ import annotations

from shopman.offering.contrib.import_export.resources import ListingItemResource, ProductResource

__all__ = ["ProductResource", "ListingItemResource"]
