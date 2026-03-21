"""Offering admin."""

from shopman.offering.admin.collection import CollectionAdmin, CollectionItemInline
from shopman.offering.admin.listing import ListingAdmin, ListingItemInline
from shopman.offering.admin.product import ProductAdmin

__all__ = [
    "CollectionAdmin",
    "CollectionItemInline",
    "ListingAdmin",
    "ListingItemInline",
    "ProductAdmin",
]
