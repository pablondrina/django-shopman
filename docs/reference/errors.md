# Referência de Exceções e Códigos de Erro

> Gerado a partir dos arquivos `exceptions.py` do código atual.

---

## Dialeto HTTP de erro (superfícies headless)

Toda resposta de erro JSON das APIs (`/api/v1/` e `/api/v1/backstage/`) fala o
mesmo dialeto, que os fronts Nuxt leem via `httpError.ts`:

```json
{
  "detail": "Escolha a data.",
  "field": "delivery_date",
  "errors": {"delivery_date": ["Escolha a data."]}
}
```

| Chave | Presença | Uso |
|-------|----------|-----|
| `detail` | **Sempre** | Mensagem humana principal (pt-br). É o que as superfícies exibem (`errorDetail`/`httpErrorMessage`). |
| `field` | Erros de campo | Roteia o erro para o passo/campo dono (ex.: `finalizar.vue` reabre o passo do checkout). Campos aninhados usam caminho pontuado (`delivery_address_structured.cep`, `items.0.sku`). |
| `errors` | Erros de validação | Mapa completo `campo → [mensagens]` para render inline. |

Implementação:

- **Erros de negócio** são construídos manualmente nas views já nesse shape.
- **Falha de serializer DRF** é convertida pelo `EXCEPTION_HANDLER` custom
  (`shopman/shop/api_errors.py`, registrado em `config/settings.py`): o shape
  DRF cru `{"phone": ["..."]}` nunca chega ao front. Mensagens dos validators
  chegam em pt-br via i18n (`LANGUAGE_CODE = "pt-br"` + locale `pt_BR` do DRF).
- **Não encontrado mapeia por TIPO de exceção**, nunca por string: `PosRecentSaleNotFound`,
  `KDSTicketNotFound`, `KDSOrderNotFound` → 404; conflito de estado
  (`OrderConflict`/`OrderStateConflict`) → 409.

### Superset do PDV (deliberado)

O POS fala um dialeto **rico** por cima do canônico — `detail` continua
obrigatório; `error` agrega metadados estáveis de recuperação
(`shopman/shop/services/pos_intent.py`):

```json
{
  "detail": "CPF/CNPJ inválido: confira os dígitos.",
  "error": {
    "code": "invalid_customer_tax_id",
    "message": "CPF/CNPJ inválido: confira os dígitos.",
    "field": "customer_tax_id",
    "focus": "customer_tax_id",
    "recovery": "Corrija o documento ou remova para emitir sem CPF."
  }
}
```

Um front que só entende o dialeto canônico continua funcionando (lê `detail`);
o operator-kit usa `error.{code,focus,recovery}` para foco e ação de 1 clique.

---

## Hierarquia

```
Exception
├── BaseError (utils)                    # Base com code + message + data
│   ├── CatalogError (offerman)
│   ├── StockError (stockman)
│   ├── CraftError (craftsman)
│   │   └── StaleRevision
│   ├── CustomerError (guestman)
│   └── AuthError (doorman)
│       └── GateError
│
├── PaymentError (payman)                # Base independente com code + context
│
├── OrderError (orderman)                # Base independente com code + context
│   ├── ValidationError
│   ├── SessionError
│   ├── CommitError
│   ├── DirectiveError
│   ├── IssueResolveError
│   ├── IdempotencyError
│   ├── IdempotencyCacheHit
│   └── InvalidTransition
│
└── RefError (orderman/refs)
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

## CatalogError (Offerman)

**Arquivo:** `packages/offerman/shopman/offerman/exceptions.py`
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

**Guia:** [offerman.md](../guides/offerman.md)

---

## StockError (Stockman)

**Arquivo:** `packages/stockman/shopman/stockman/exceptions.py`
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

**Guia:** [stockman.md](../guides/stockman.md)

---

## CraftError (Craftsman)

**Arquivo:** `packages/craftsman/shopman/craftsman/exceptions.py`
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

**Guia:** [craftsman.md](../guides/craftsman.md)

---

## CustomerError (Guestman)

**Arquivo:** `packages/guestman/shopman/guestman/exceptions.py`
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

**Guia:** [guestman.md](../guides/guestman.md)

---

## AuthError (Doorman)

**Arquivo:** `packages/doorman/shopman/doorman/exceptions.py`
**Base:** `BaseError`

| Código | Quando ocorre |
|--------|--------------|
| `TOKEN_INVALID` | Bridge token inválido, expirado ou já usado |
| `CODE_INVALID` | Código de verificação incorreto ou expirado |
| `RATE_LIMIT` | Limite de taxa excedido (muitos códigos/tentativas) |
| `GATE_FAILED` | Gate genérico falhou (via `GateError`) |

**Subclasse:** `GateError(AuthError)` — levantada com `gate_name` e `code="GATE_FAILED"`. Usada pelos gates individuais.

**Guia:** [doorman.md](../guides/doorman.md)

---

## PaymentError (Payman)

**Arquivo:** `packages/payman/shopman/payman/exceptions.py`
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

## OrderError (Orderman)

**Arquivo:** `packages/orderman/shopman/orderman/exceptions.py`
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

**Guia:** [orderman.md](../guides/orderman.md)

---

## RefError (Ordering — Refs)

**Arquivo:** `packages/orderman/shopman/ordering/contrib/refs/exceptions.py`
**Base:** `Exception`

| Exceção | Quando ocorre |
|---------|--------------|
| `RefTypeNotFound(slug)` | Tipo de referência não registrado |
| `RefScopeInvalid(missing_keys, ref_type_slug)` | Chaves de escopo ausentes na referência |
| `RefConflict(ref_type_slug, value, existing_target_kind, existing_target_id)` | Referência já aponta para outro alvo |

---

## Padrão de Uso

```python
from shopman.stockman.exceptions import StockError

try:
    stock.hold(sku="PAO-FR", qty=10)
except StockError as e:
    if e.code == "INSUFFICIENT_AVAILABLE":
        print(f"Disponível: {e.available}, Pedido: {e.requested}")
    print(e.as_dict())
    # {"code": "INSUFFICIENT_AVAILABLE", "message": "...", "available": 5, "requested": 10}
```
