"""
Exceptions for Stocking.

All errors are StockError with a structured code for programmatic handling.
"""

from decimal import Decimal
from typing import Any

from shopman.utils.exceptions import BaseError


class StockError(BaseError):
    """
    Structured exception for stock operations.

    Usage:
        try:
            stock.hold(10, produto, sexta)
        except StockError as e:
            if e.code == 'INSUFFICIENT_AVAILABLE':
                print(f"Só tem {e.available} disponível")

    Attributes:
        code: Error code for programmatic handling
        message: Human-readable message
        data: Additional context data
    """

    _default_messages = {
        'INSUFFICIENT_AVAILABLE': 'Quantidade solicitada indisponível',
        'INSUFFICIENT_QUANTITY': 'Quantidade insuficiente no estoque',
        'INVALID_HOLD': 'Bloqueio inválido ou não encontrado',
        'INVALID_STATUS': 'Status inválido para esta operação',
        'INVALID_QUANTITY': 'Quantidade inválida (deve ser positiva)',
        'HOLD_IS_DEMAND': 'Bloqueio é demanda (sem estoque vinculado)',
        'HOLD_EXPIRED': 'Bloqueio expirado',
        'REASON_REQUIRED': 'Motivo é obrigatório',
        'QUANT_NOT_FOUND': 'Estoque não encontrado',
        'CONCURRENT_MODIFICATION': 'Modificação concorrente detectada',
    }

    @property
    def available(self) -> Decimal:
        """Shortcut for data['available']."""
        return self.data.get('available', Decimal('0'))

    @property
    def requested(self) -> Decimal:
        """Shortcut for data['requested']."""
        return self.data.get('requested', Decimal('0'))

    def as_dict(self) -> dict[str, Any]:
        """Serialize to dict (useful for APIs)."""
        return {
            'code': self.code,
            'message': self.message,
            'data': {
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in self.data.items()
            }
        }
