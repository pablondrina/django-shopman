"""Typed exceptions raised by backstage mutation services."""

from __future__ import annotations


class BackstageServiceError(Exception):
    """Base class for operator-surface service errors."""


class AlertError(BackstageServiceError):
    """Raised when an alert mutation cannot be applied."""


class KDSError(BackstageServiceError):
    """Raised when a KDS mutation cannot be applied."""


class KDSTicketNotFound(KDSError):
    """Ticket inexistente.

    A camada HTTP mapeia por TIPO para 404 (recurso não existe), nunca 400 —
    mesmo padrão de ``PosRecentSaleNotFound``.
    """


class KDSOrderNotFound(KDSError):
    """Pedido inexistente numa ação de expedição. A camada HTTP mapeia para 404."""


class OrderError(BackstageServiceError):
    """Raised when an order mutation cannot be applied."""


class OrderConflict(OrderError):
    """Raised when the order changed state before the operator action landed.

    Ex.: recusar um pedido que a auto-confirmação acabou de confirmar. A camada
    HTTP mapeia para 409 (conflito de estado), não 400 (request inválido).
    """


class POSError(BackstageServiceError):
    """Raised when a POS mutation cannot be applied."""


class POSPermissionError(POSError):
    """Raised when a POS actor lacks permission (ex.: fechar caixa de outro)."""


class ProductionError(BackstageServiceError):
    """Raised when a production mutation cannot be applied."""


class CatalogError(BackstageServiceError):
    """Raised when a catalog mutation cannot be applied."""


class AiAssistNotConfigured(BackstageServiceError):
    """Assist de IA sem credencial.

    A camada HTTP mapeia por TIPO para 503 (dependência indisponível), nunca 400 —
    o pedido do operador estava certo; falta configuração no deployment.
    """


class AiAssistError(BackstageServiceError):
    """Raised when the AI assist call fails (provider error, empty completion)."""
