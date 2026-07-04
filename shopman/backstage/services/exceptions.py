"""Typed exceptions raised by backstage mutation services."""

from __future__ import annotations


class BackstageServiceError(Exception):
    """Base class for operator-surface service errors."""


class AlertError(BackstageServiceError):
    """Raised when an alert mutation cannot be applied."""


class KDSError(BackstageServiceError):
    """Raised when a KDS mutation cannot be applied."""


class OrderError(BackstageServiceError):
    """Raised when an order mutation cannot be applied."""


class POSError(BackstageServiceError):
    """Raised when a POS mutation cannot be applied."""


class POSPermissionError(POSError):
    """Raised when a POS actor lacks permission (ex.: fechar caixa de outro)."""


class ProductionError(BackstageServiceError):
    """Raised when a production mutation cannot be applied."""


class CatalogError(BackstageServiceError):
    """Raised when a catalog mutation cannot be applied."""
