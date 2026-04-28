"""Typed exceptions raised by backstage command services."""

from __future__ import annotations


class BackstageServiceError(Exception):
    """Base class for operator-surface service errors."""


class AlertError(BackstageServiceError):
    """Raised when an alert command cannot be applied."""


class KDSError(BackstageServiceError):
    """Raised when a KDS command cannot be applied."""


class OrderError(BackstageServiceError):
    """Raised when an order command cannot be applied."""


class POSError(BackstageServiceError):
    """Raised when a POS command cannot be applied."""


class ProductionError(BackstageServiceError):
    """Raised when a production command cannot be applied."""
