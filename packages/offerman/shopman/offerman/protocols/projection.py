"""
Catalog projection protocol.

Defines the contract for projecting the internal catalog to external
channels (e.g. iFood, Rappi, Uber Eats, marketplace APIs).

An implementation receives a normalized snapshot of the sellable catalog
and pushes it to an external system. The framework or instance provides
concrete implementations; offerman only defines the contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ProjectedItem:
    """
    Normalized representation of a catalog item for external projection.

    All prices in centavos (_q convention).
    """

    sku: str
    name: str
    description: str
    unit: str
    price_q: int
    is_published: bool
    is_sellable: bool
    category: str | None = None
    image_url: str | None = None
    keywords: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectionResult:
    """Result of a catalog projection operation."""

    success: bool
    projected: int = 0
    errors: list[str] = field(default_factory=list)
    channel: str = ""


@runtime_checkable
class CatalogProjectionBackend(Protocol):
    """
    Contract for projecting the catalog to an external channel.

    Implementations push catalog state to third-party systems.
    The offerman package defines this contract; concrete implementations
    live in the framework or instance layer.
    """

    def project(
        self,
        items: list[ProjectedItem],
        *,
        channel: str,
        full_sync: bool = False,
    ) -> ProjectionResult:
        """
        Project catalog items to an external channel.

        Args:
            items: Normalized catalog items to project.
            channel: Target channel identifier.
            full_sync: If True, replace the entire catalog; if False, upsert only.

        Returns:
            ProjectionResult with success status and error details.
        """
        ...

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        """
        Remove items from an external channel.

        Args:
            skus: SKUs to retract.
            channel: Target channel identifier.

        Returns:
            ProjectionResult with success status.
        """
        ...
