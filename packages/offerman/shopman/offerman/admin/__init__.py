"""Offering admin."""

from shopman.offerman.admin.collection import CollectionAdmin, CollectionItemInline
from shopman.offerman.admin.listing import ListingAdmin, ListingItemInline
from shopman.offerman.admin.product import ProductAdmin

__all__ = [
    "CollectionAdmin",
    "CollectionItemInline",
    "ListingAdmin",
    "ListingItemInline",
    "ProductAdmin",
]
