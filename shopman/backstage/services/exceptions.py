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


class ProductionError(BackstageServiceError):
    """Raised when a production mutation cannot be applied."""
