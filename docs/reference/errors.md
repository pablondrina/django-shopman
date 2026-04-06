# Referência de Exceções e Códigos de Erro

> Gerado a partir dos arquivos `exceptions.py` do código atual.

---

## Hierarquia

```
Exception
├── BaseError (utils)                    # Base com code + message + data
│   ├── CatalogError (offering)
│   ├── StockError (stocking)
│   ├── CraftError (crafting)
│   │   └── StaleRevision
│   ├── CustomersError (customers)
│   └── AuthError (auth)
│       └── GateError
│
├── PaymentError (payments)              # Base independente com code + context
│
├── OrderingError (ordering)             # Base independente com code + context
│   ├── ValidationError
│   ├── SessionError
│   ├── CommitError
│   ├── DirectiveError
│   ├── IssueResolveError
│   ├── IdempotencyError
│   ├── IdempotencyCacheHit
│   └── InvalidTransition
│
└── RefError (ordering/refs)
    ├── RefTypeNotFound
    ├── RefScopeInvalid
    └── RefConflict
```

---

## BaseError (Utils)

**Arquivo:** `packages/utils/shopman/utils/exceptions.py`

Classe base que todas as exceções de domínio dos core apps herdam. Oferece serialização via `as_dict()`.

```python
raise BaseError(code="SOME_CODE", message="descrição", extra_key="valor")
# .as_dict() → {"code": "SOME_CODE", "message": "descrição", "extra_key": "valor"}
```

---

## CatalogError (Offering)

**Arquivo:** `packages/offerman/shopman/offering/exceptions.py`
**Base:** `BaseError`
**Propriedade:** `.sku` — extrai SKU dos dados

| Código | Quando ocorre |
|--------|--------------|
| `SKU_NOT_FOUND` | SKU não encontrado no catálogo |
| `SKU_INACTIVE` | Produto existe mas está inativo |
| `NOT_A_BUNDLE` | Tentativa de expandir produto que não é bundle |
| `INVALID_PRICE_LIST` | Listing referenciado não existe |
| `PRICE_LIST_EXPIRED` | Listing expirou |
| `INVALID_QUANTITY` | Quantidade inválida (≤ 0) |
| `CIRCULAR_COMPONENT` | Ciclo detectado na árvore de componentes do bundle |

**Guia:** [offering.md](../guides/offering.md)

---

## StockError (Stocking)

**Arquivo:** `packages/stockman/shopman/stocking/exceptions.py`
**Base:** `BaseError`
**Propriedades:** `.available`, `.requested` — quantidades para erros de insuficiência

| Código | Quando ocorre |
|--------|--------------|
| `INSUFFICIENT_AVAILABLE` | Quantidade disponível insuficiente para hold/move |
| `INSUFFICIENT_QUANTITY` | Quantidade insuficiente para operação genérica |
| `INVALID_HOLD` | Hold não encontrado ou em estado inválido |
| `INVALID_STATUS` | Transição de status inválida |
| `INVALID_QUANTITY` | Quantidade ≤ 0 |
| `HOLD_IS_DEMAND` | Tentativa de operação inválida em hold de demanda |
| `HOLD_EXPIRED` | Hold expirou antes da operação |
| `REASON_REQUIRED` | Motivo obrigatório para ajuste de estoque |
| `QUANT_NOT_FOUND` | Quant não encontrado na posição/SKU |
| `CONCURRENT_MODIFICATION` | Conflito de concorrência (optimistic locking) |

**Guia:** [stocking.md](../guides/stocking.md)

---

## CraftError (Crafting)

**Arquivo:** `packages/craftsman/shopman/crafting/exceptions.py`
**Base:** `BaseError`

| Código | Quando ocorre |
|--------|--------------|
| `INVALID_QUANTITY` | Quantidade ≤ 0 para work order |
| `TERMINAL_STATUS` | Work order já em estado terminal (DONE/VOID) |
| `VOID_FROM_DONE` | Tentativa de anular work order já concluída |
| `STALE_REVISION` | Conflito de concorrência — revisão esperada não bate |
| `BOM_CYCLE` | Ciclo detectado na árvore BOM de receita |
| `RECIPE_NOT_FOUND` | Receita não encontrada |
| `WORK_ORDER_NOT_FOUND` | Work order não encontrada |

**Subclasse:** `StaleRevision(CraftError)` — levantada com `code="STALE_REVISION"` automaticamente, recebe `(order, expected_rev)`.

**Guia:** [crafting.md](../guides/crafting.md)

---

## CustomersError (Customers)

**Arquivo:** `packages/guestman/shopman/customers/exceptions.py`
**Base:** `BaseError`

| Código | Quando ocorre |
|--------|--------------|
| `CUSTOMER_NOT_FOUND` | Cliente não encontrado pelo ref |
| `ADDRESS_NOT_FOUND` | Endereço não encontrado para o cliente |
| `DUPLICATE_CONTACT` | Contato (telefone/email) já associado a outro cliente |
| `INVALID_PHONE` | Telefone não passou na validação (formato E.164) |
| `MERGE_DENIED` | Merge de clientes negado (requer validação prévia) |
| `CONSENT_NOT_FOUND` | Registro de consentimento não encontrado |
| `LOYALTY_NOT_ENROLLED` | Cliente não está inscrito no programa de fidelidade |
| `LOYALTY_INSUFFICIENT_POINTS` | Pontos insuficientes para resgate |

**Guia:** [customers.md](../guides/customers.md)

---

## AuthError (Auth)

**Arquivo:** `packages/doorman/shopman/auth/exceptions.py`
**Base:** `BaseError`

| Código | Quando ocorre |
|--------|--------------|
| `TOKEN_INVALID` | Bridge token inválido, expirado ou já usado |
| `CODE_INVALID` | Código de verificação incorreto ou expirado |
| `RATE_LIMIT` | Limite de taxa excedido (muitos códigos/tentativas) |
| `GATE_FAILED` | Gate genérico falhou (via `GateError`) |

**Subclasse:** `GateError(AuthError)` — levantada com `gate_name` e `code="GATE_FAILED"`. Usada pelos gates individuais.

**Guia:** [auth.md](../guides/auth.md)

---

## PaymentError (Payments)

**Arquivo:** `packages/payman/shopman/payments/exceptions.py`
**Base:** `Exception` (independente de `BaseError`)
**Construtor:** `__init__(code, message, context=None)`
**Serialização:** `.as_dict()` → `{"code": "...", "message": "...", "context": {...}}`

| Código | Quando ocorre |
|--------|--------------|
| `INTENT_NOT_FOUND` | Intent não encontrado pelo ref |
| `INVALID_TRANSITION` | Transição de status não permitida |
| `ALREADY_CAPTURED` | Intent já foi capturado |
| `ALREADY_REFUNDED` | Intent já foi totalmente reembolsado |
| `AMOUNT_EXCEEDS_CAPTURED` | Refund maior que o capturado |
| `CAPTURE_EXCEEDS_AUTHORIZED` | Capture maior que o autorizado |
| `INTENT_EXPIRED` | Intent expirado |

---

## OrderingError (Ordering)

**Arquivo:** `packages/omniman/shopman/ordering/exceptions.py`
**Base:** `Exception` (independente de `BaseError`)
**Construtor:** `__init__(code, message, context=None)`

### ValidationError

| Código | Quando ocorre |
|--------|--------------|
| `missing_sku` | SKU ausente no item |
| `invalid_qty` | Quantidade inválida |
| `unsupported_op` | Operação não suportada pelo canal |

### SessionError

| Código | Quando ocorre |
|--------|--------------|
| `not_found` | Sessão não encontrada |
| `already_committed` | Sessão já foi commitada |
| `already_abandoned` | Sessão já foi abandonada |
| `locked` | Sessão está travada para edição |

### CommitError

| Código | Quando ocorre |
|--------|--------------|
| `blocking_issues` | Issues bloqueantes não resolvidas |
| `stale_checks` | Checks de pré-commit desatualizados |
| `missing_check` | Check obrigatório não executado |
| `hold_expired` | Hold de estoque expirou durante commit |
| `already_committed` | Sessão já commitada |

### DirectiveError

| Código | Quando ocorre |
|--------|--------------|
| `no_handler` | Nenhum handler registrado para o tópico |
| `handler_failed` | Handler falhou durante execução |

### IssueResolveError

| Código | Quando ocorre |
|--------|--------------|
| `issue_not_found` | Issue não encontrada na sessão |
| `no_resolver` | Nenhum resolver registrado para o tipo |
| `action_not_found` | Ação de resolução não encontrada |
| `stale_action` | Ação de resolução desatualizada |
| `resolver_error` | Erro durante resolução |

### IdempotencyError

| Código | Quando ocorre |
|--------|--------------|
| `in_progress` | Operação idempotente já em execução |
| `conflict` | Conflito de chave de idempotência |

### IdempotencyCacheHit

Não é erro — controle de fluxo. Contém `cached_response` com resultado anterior.

### InvalidTransition

| Código | Quando ocorre |
|--------|--------------|
| `invalid_transition` | Transição de status não permitida |
| `terminal_status` | Pedido em status terminal, não aceita transições |

**Guia:** [ordering.md](../guides/ordering.md)

---

## RefError (Ordering — Refs)

**Arquivo:** `packages/omniman/shopman/ordering/contrib/refs/exceptions.py`
**Base:** `Exception`

| Exceção | Quando ocorre |
|---------|--------------|
| `RefTypeNotFound(slug)` | Tipo de referência não registrado |
| `RefScopeInvalid(missing_keys, ref_type_slug)` | Chaves de escopo ausentes na referência |
| `RefConflict(ref_type_slug, value, existing_target_kind, existing_target_id)` | Referência já aponta para outro alvo |

---

## Padrão de Uso

```python
from shopman.stocking.exceptions import StockError

try:
    stock.hold(sku="PAO-FR", qty=10)
except StockError as e:
    if e.code == "INSUFFICIENT_AVAILABLE":
        print(f"Disponível: {e.available}, Pedido: {e.requested}")
    print(e.as_dict())
    # {"code": "INSUFFICIENT_AVAILABLE", "message": "...", "available": 5, "requested": 10}
```
