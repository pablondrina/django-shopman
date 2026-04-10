"""
Payment Exceptions.

Todas as exceções seguem o padrão:
- code: Código máquina do erro
- message: Mensagem legível para humanos
- context: Dados adicionais sobre o erro
"""

from __future__ import annotations


class PaymentError(Exception):
    """
    Classe base para todas as exceções do Payman.

    Codes:
        INTENT_NOT_FOUND — Intent não encontrado pelo ref
        INVALID_TRANSITION — Transição de status não permitida
        ALREADY_CAPTURED — Intent já foi capturado
        ALREADY_REFUNDED — Intent já foi totalmente reembolsado
        AMOUNT_EXCEEDS_CAPTURED — Refund maior que o capturado
        CAPTURE_EXCEEDS_AUTHORIZED — Capture maior que o autorizado
        INTENT_EXPIRED — Intent expirado
    """

    def __init__(self, code: str = "error", message: str = "", context: dict | None = None):
        self.code = code
        self.message = message or code
        self.context = context or {}
        super().__init__(f"[{code}] {self.message}")

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "context": self.context}
