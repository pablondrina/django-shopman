# ADR-010 — Contrato handler↔dispatch e roadmap de autodiscovery

**Status:** Aceito
**Data:** 2026-04-24
**Escopo:** Contrato entre directive handlers e dispatch layer (dispatch.py / process_directives.py)

---

## Contexto

Até CC-3, cada handler era responsável por gerenciar o estado do Directive diretamente: setar `message.status = "done"` no sucesso, `"failed"` no erro terminal, `"queued"` no retry, incrementar `message.attempts`, calcular backoff, e chamar `message.save()`. Isso resultava em ~130 linhas de lógica de estado duplicada across 9 handlers, com inconsistências (e.g. loyalty usando `"completed"` em vez de `"done"`, handlers com retry manual diferente do dispatch layer).

O `register_all()` em `handlers/__init__.py` (302 linhas, 16 funções de registro) e o `apps.py` (188 linhas, 8 métodos em `ready()`) concentram todo o wiring. Adicionar um handler exige editar 2 a 3 pontos em `__init__.py` + a entrada em `ALL_HANDLERS`. O orquestrador conhece detalhes de cada package.

## Decisão

### 1. Contrato handler↔dispatch (implementado em CC-3)

Um handler é qualquer objeto com `topic: str` e `handle(*, message: Directive, ctx: dict) -> None`.

**Regras do contrato:**

| Cenário | Handler faz | Dispatch faz |
|---------|------------|-------------|
| **Sucesso** | `return` (nenhuma mutação de status) | `refresh_from_db()` → se `status == "running"`, seta `"done"` |
| **Erro terminal** (dado inválido, recurso inexistente) | `raise DirectiveTerminalError("...")` | Seta `"failed"`, `error_code="terminal"`, grava `last_error` |
| **Erro transiente** (rede, lock, API fora) | `raise DirectiveTransientError("...")` | Se `attempts < MAX_ATTEMPTS`: requeue com backoff `2^n`. Senão: `"failed"` |
| **Deferral** (esperar horário, rate limit) | Seta `message.status = "queued"` + `message.available_at`, chama `save()`, depois `return` | `refresh_from_db()` → vê `status != "running"`, não sobrescreve |
| **Skip/noop** (idempotente, já processado) | `return` | Mesmo que sucesso: seta `"done"` |

**O handler NUNCA:**
- Seta `message.status = "done"` ou `"failed"` (exceto o pattern de deferral com `"queued"`)
- Incrementa `message.attempts` (dispatch já faz antes de chamar o handler)
- Calcula backoff (dispatch é o dono do backoff exponencial)
- Chama `message.save(update_fields=["status", ...])` para sucesso/falha

**Exceções importadas de:** `shopman.orderman.exceptions`
- `DirectiveTerminalError(message, context=None)` — irrecuperável, `error_code="terminal"`
- `DirectiveTransientError(message, context=None)` — recuperável, `error_code="transient"`

### 2. Autodiscovery (roadmap — pós-produção)

**Estado atual:** `register_all()` tem 16 funções `_register_*` que importam e instanciam handlers explicitamente. `ALL_HANDLERS` é um manifesto flat que serve como documentação mas não é usado no registro.

**Target (futuro):**

```python
# handlers/__init__.py — target
def register_all() -> None:
    for handler_path in ALL_HANDLERS:
        module_path, class_name = handler_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        handler_cls = getattr(module, class_name)
        # Guard: optional handlers check their own config
        instance = _instantiate(handler_cls)
        if instance is not None:
            registry.register_directive_handler(instance)
```

Cada handler que precisa de backend injeta via `__init__` com guard:

```python
class NFCeEmitHandler:
    topic = FISCAL_EMIT_NFCE

    def __init__(self, backend: FiscalBackend | None = None):
        if backend is None:
            backend = _resolve_fiscal_backend()  # raises if configured-but-wrong
        self.backend = backend
```

**Constraints que impedem fazer agora:**
1. **Boot order**: pricing modifiers devem registrar antes de validators. Autodiscovery precisa de mecanismo de ordering (e.g. `order` attribute ou topo-sort).
2. **Backends injetados**: fiscal, accounting, catalog_projection recebem backends no `__init__`. Autodiscovery precisa de um resolver que sabe qual backend injetar.
3. **Signal wiring**: `_register_stock_signals()`, `_register_catalog_signals()`, `_register_sse_emitters()` fazem wiring de signals, não de handlers. Esses devem permanecer explícitos.
4. **Notification backends**: `_register_notification_handlers()` registra notification backends além do handler. Isso é wiring do notification framework, não do directive registry.

**Decisão:** Defer para pós-produção. O contrato handler↔dispatch (seção 1) é o que importa agora — ele elimina a inconsistência independente de como handlers são registrados.

## Consequências

### Positivas

- **Handlers finos**: lógica de negócio apenas, sem boilerplate de estado. Média de -15 linhas por handler.
- **Consistência garantida**: um único code path para backoff, retry, e transição de estado.
- **Testabilidade**: handlers podem ser testados com `assertRaises(DirectiveTerminalError)` em vez de verificar `message.status` após a call.
- **Deferral explícito**: o pattern `status="queued" + available_at` é o único caso onde o handler toca status, e é intencional e visível.

### Negativas

- **Handlers com side-effects pré-erro**: se o handler faz efeitos colaterais (e.g. salva dados no Order) antes de falhar, o `raise` não desfaz esses efeitos. Handlers devem garantir idempotência ou usar `transaction.atomic()`.
- **Autodiscovery adiada**: o `register_all()` continua verboso. Mas a verbosidade é de wiring, não de lógica — é inofensiva.

### Mitigações

- Handlers com side-effects críticos devem wrappear em `transaction.atomic()` (já feito em `returns.py`).
- O manifesto `ALL_HANDLERS` continua como documentação. Quando autodiscovery for implementada, ele vira a source of truth real.

## Referências

- [ADR-003 — Directives sem Celery](adr-003-directives-sem-celery.md) — contexto sobre o modelo de fila
- [packages/orderman/shopman/orderman/dispatch.py](../../packages/orderman/shopman/orderman/dispatch.py) — dispatch layer (CC-3)
- [packages/orderman/shopman/orderman/exceptions.py](../../packages/orderman/shopman/orderman/exceptions.py) — DirectiveTerminalError, DirectiveTransientError
- [docs/plans/CONTRACT-CONSOLIDATION-PLAN.md](../plans/CONTRACT-CONSOLIDATION-PLAN.md) — plano que originou esta ADR (CC-5)
