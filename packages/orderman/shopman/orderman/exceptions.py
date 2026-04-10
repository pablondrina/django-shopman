"""
Orderman Exceptions.

Todas as exceções seguem o padrão:
- code: Código máquina do erro (ex.: "missing_sku", "invalid_qty")
- message: Mensagem legível para humanos
- context: Dados adicionais sobre o erro
"""

from __future__ import annotations


class OrderingError(Exception):
    """
    Classe base para todas as exceções do Orderman.

    Attributes:
        code: Código máquina do erro
        message: Mensagem legível para humanos
        context: Dados adicionais sobre o erro
    """

    def __init__(self, code: str = "error", message: str = "", context: dict | None = None):
        self.code = code
        self.message = message or code
        self.context = context or {}
        super().__init__(f"[{code}] {self.message}")

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "context": self.context}


class ValidationError(OrderingError):
    """
    Erro de validação (Validator falhou).

    Codes: "missing_sku", "invalid_qty", "unsupported_op", etc.
    """


class SessionError(OrderingError):
    """
    Erro relacionado a sessões.

    Codes: "not_found", "already_committed", "already_abandoned", "locked"
    """


class CommitError(OrderingError):
    """
    Erro durante o commit de uma sessão.

    Codes: "blocking_issues", "stale_checks", "missing_check", "hold_expired", "already_committed"
    """


class DirectiveError(OrderingError):
    """
    Erro durante processamento de diretiva.

    Codes: "no_handler", "handler_failed"
    """


class DirectiveTransientError(DirectiveError):
    """
    Falha recuperável durante processamento de diretiva (network, lock timeout, etc).

    O worker mantém a diretiva em fila com backoff exponencial para retry.
    Valor de error_code gravado: "transient"
    """

    def __init__(self, message: str = "", context: dict | None = None):
        super().__init__(code="transient", message=message, context=context)


class DirectiveTerminalError(DirectiveError):
    """
    Falha irrecuperável durante processamento de diretiva (dado inválido, lógica quebrada).

    O worker marca a diretiva como failed sem retry.
    Valor de error_code gravado: "terminal"
    """

    def __init__(self, message: str = "", context: dict | None = None):
        super().__init__(code="terminal", message=message, context=context)


class IssueResolveError(OrderingError):
    """
    Erro durante resolução de issue.

    Codes: "issue_not_found", "no_resolver", "action_not_found", "stale_action", "resolver_error"
    """


class IdempotencyError(OrderingError):
    """
    Erro relacionado a idempotência.

    Codes: "in_progress", "conflict"
    """


class IdempotencyCacheHit(OrderingError):
    """
    Indica que resposta foi encontrada em cache de idempotência.

    NÃO é um erro - é um fluxo de controle para retornar resposta cacheada.

    Attributes:
        cached_response: A resposta cacheada do commit anterior
    """

    def __init__(self, cached_response: dict):
        self.cached_response = cached_response
        super().__init__("Idempotency cache hit")


class InvalidTransition(OrderingError):
    """
    Erro de transição de status inválida.

    Codes: "invalid_transition", "terminal_status"
    """
