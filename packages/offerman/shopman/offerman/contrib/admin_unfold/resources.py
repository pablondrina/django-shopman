"""Re-export resources from shopman.offerman.contrib.import_export for backwards compatibility."""
from __future__ import annotations

from shopman.offerman.contrib.import_export.resources import ListingItemResource, ProductResource

__all__ = ["ProductResource", "ListingItemResource"]
