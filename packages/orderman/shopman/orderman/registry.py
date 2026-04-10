"""
Orderman Registry — Sistema de extensibilidade via Protocols e Registry.

Permite registrar validators, modifiers, directive handlers e issue resolvers.
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable, Any


# =============================================================================
# PROTOCOLS
# =============================================================================


@runtime_checkable
class Validator(Protocol):
    """
    Gate binário (pass/fail). Não muta estado nem faz IO.

    Stages:
    - "draft": validação durante edição
    - "commit": validação no momento do commit
    - "import": validação ao importar pedido externo
    """

    code: str
    stage: str  # "draft" | "commit" | "import"

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        """Raises ValidationError if invalid."""
        ...


@runtime_checkable
class Modifier(Protocol):
    """
    Transformação determinística e idempotente. Não faz IO.

    `order` define a sequência de execução (menor = primeiro).
    """

    code: str
    order: int

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        """Mutates session in-place. No IO."""
        ...


@runtime_checkable
class DirectiveHandler(Protocol):
    """
    Handler para processamento de diretivas (at-least-once).
    Handlers devem ser idempotentes pois podem ser executados múltiplas vezes.
    """

    topic: str

    def handle(self, *, message: Any, ctx: dict) -> None:
        """Processes directive. May do IO."""
        ...


@runtime_checkable
class IssueResolver(Protocol):
    """
    Resolver para issues de uma determinada source.

    O Kernel delega resolução para o resolver registrado pela `source` da issue.
    """

    source: str

    def resolve(self, *, session: Any, issue: dict, action_id: str, ctx: dict) -> Any:
        """Resolves issue by applying action. Returns updated session."""
        ...


@runtime_checkable
class Check(Protocol):
    """
    Par directive + validator para verificações pré-commit.

    O Check DECLARA o par. Não faz IO nem valida diretamente.
    O ModifyService cria a directive (topic). O CommitService chama validate().
    """

    code: str
    topic: str  # directive topic para a preparação (IO)

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        """Gate puro — valida o resultado da preparação. Sem IO."""
        ...


# =============================================================================
# REGISTRY
# =============================================================================


class _Registry:
    """
    Registro central de extensões do Orderman.

    Uso:
        from shopman.orderman import registry

        registry.register_validator(MyValidator())
        registry.register_modifier(MyModifier())
        registry.register_directive_handler(MyHandler())
        registry.register_issue_resolver(MyResolver())
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._validators: list[Validator] = []
        self._modifiers: list[Modifier] = []
        self._directive_handlers: dict[str, DirectiveHandler] = {}
        self._issue_resolvers: dict[str, IssueResolver] = {}
        self._checks: dict[str, Check] = {}

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------

    def register_validator(self, validator: Validator) -> None:
        if not isinstance(validator, Validator):
            raise TypeError(f"Expected Validator protocol, got {type(validator)}")
        with self._lock:
            self._validators.append(validator)

    def get_validators(self, stage: str | None = None) -> list[Validator]:
        with self._lock:
            if stage is None:
                return list(self._validators)
            return [v for v in self._validators if v.stage == stage]

    # -------------------------------------------------------------------------
    # Modifiers
    # -------------------------------------------------------------------------

    def register_modifier(self, modifier: Modifier) -> None:
        if not isinstance(modifier, Modifier):
            raise TypeError(f"Expected Modifier protocol, got {type(modifier)}")
        with self._lock:
            self._modifiers.append(modifier)

    def get_modifiers(self) -> list[Modifier]:
        with self._lock:
            return sorted(self._modifiers, key=lambda m: m.order)

    # -------------------------------------------------------------------------
    # Directive Handlers
    # -------------------------------------------------------------------------

    def register_directive_handler(self, handler: DirectiveHandler) -> None:
        if not isinstance(handler, DirectiveHandler):
            raise TypeError(f"Expected DirectiveHandler protocol, got {type(handler)}")
        with self._lock:
            if handler.topic in self._directive_handlers:
                raise ValueError(f"Handler for topic '{handler.topic}' already registered")
            self._directive_handlers[handler.topic] = handler

    def get_directive_handler(self, topic: str) -> DirectiveHandler | None:
        with self._lock:
            return self._directive_handlers.get(topic)

    def get_directive_handlers(self) -> dict[str, DirectiveHandler]:
        with self._lock:
            return dict(self._directive_handlers)

    # -------------------------------------------------------------------------
    # Issue Resolvers
    # -------------------------------------------------------------------------

    def register_issue_resolver(self, resolver: IssueResolver) -> None:
        if not isinstance(resolver, IssueResolver):
            raise TypeError(f"Expected IssueResolver protocol, got {type(resolver)}")
        with self._lock:
            if resolver.source in self._issue_resolvers:
                raise ValueError(f"Resolver for source '{resolver.source}' already registered")
            self._issue_resolvers[resolver.source] = resolver

    def get_issue_resolver(self, source: str) -> IssueResolver | None:
        with self._lock:
            return self._issue_resolvers.get(source)

    def get_issue_resolvers(self) -> dict[str, IssueResolver]:
        with self._lock:
            return dict(self._issue_resolvers)

    # -------------------------------------------------------------------------
    # Checks
    # -------------------------------------------------------------------------

    def register_check(self, check: Check) -> None:
        if not isinstance(check, Check):
            raise TypeError(f"Expected Check protocol, got {type(check)}")
        with self._lock:
            if check.code in self._checks:
                raise ValueError(f"Check '{check.code}' already registered")
            self._checks[check.code] = check

    def get_check(self, code: str) -> Check | None:
        with self._lock:
            return self._checks.get(code)

    def get_checks(self) -> dict[str, Check]:
        with self._lock:
            return dict(self._checks)

    # -------------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------------

    def clear(self) -> None:
        """Limpa todos os registros. Útil para testes."""
        with self._lock:
            self._validators.clear()
            self._modifiers.clear()
            self._directive_handlers.clear()
            self._issue_resolvers.clear()
            self._checks.clear()


# Instância global do registry
_registry = _Registry()

# API pública — funções delegam para a instância global
register_validator = _registry.register_validator
get_validators = _registry.get_validators
register_modifier = _registry.register_modifier
get_modifiers = _registry.get_modifiers
register_directive_handler = _registry.register_directive_handler
get_directive_handler = _registry.get_directive_handler
get_directive_handlers = _registry.get_directive_handlers
register_issue_resolver = _registry.register_issue_resolver
get_issue_resolver = _registry.get_issue_resolver
get_issue_resolvers = _registry.get_issue_resolvers
register_check = _registry.register_check
get_check = _registry.get_check
get_checks = _registry.get_checks
clear = _registry.clear
reset = _registry.clear  # Alias para testes
