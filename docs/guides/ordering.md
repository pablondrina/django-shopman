# Ordering — Pedidos e Sessões

## Visão Geral

O app `shopman.ordering` gerencia o ciclo completo de pedidos: sessões de compra, commit atômico, directives pós-commit, máquina de estados e fulfillment. A arquitetura é baseada em canais, com registry de validators, modifiers e directive handlers.

## Conceitos

### Canal (`Channel`)
Origem do pedido (balcão, WhatsApp, iFood). Define políticas de preço, edição, fluxo de confirmação e directives pós-commit.

### Sessão (`Session`)
Carrinho de compras temporário num canal. Estado: `open → committed` ou `abandoned`.

### Commit
Transformação atômica de Session em Order. Pipeline: validações → criação do pedido → snapshot → enfileiramento de directives.

### Directive
Comando assíncrono pós-commit (ex: `stock.hold`, `notification.send`). Processado por handlers registrados via topic.

### Idempotência
Cada commit tem uma `idempotency_key` que previne duplicação. Requests duplicados retornam o resultado cacheado.

## Modelos

### Channel

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | CharField(64, unique) | Código do canal (ex: "shop", "whatsapp") |
| `name` | CharField(128) | Nome legível |
| `pricing_policy` | CharField | "internal" ou "external" |
| `edit_policy` | CharField | "open" ou "locked" |
| `config` | JSONField | Configuração completa (preset, stock, payment, etc.) |
| `is_active` | BooleanField | Ativo |

**Config keys:** `preset`, `stock`, `payment`, `confirmation_flow`, `post_commit_directives`, `notification_routing`, `status_flow`, `required_checks_on_commit`, etc.

### Session

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `session_key` | CharField(64) | Chave da sessão |
| `channel` | FK(Channel) | Canal de origem |
| `handle_type` | CharField(32, null) | Tipo do identificador (ex: "table", "customer_id") |
| `handle_ref` | CharField(64, null) | Valor do identificador |
| `state` | CharField | "open", "committed", "abandoned" |
| `pricing_policy` | CharField | "internal" ou "external" |
| `edit_policy` | CharField | "open" ou "locked" |
| `rev` | IntegerField | Contador de revisão |
| `data` | JSONField | checks, issues, customer, delivery info |
| `pricing` | JSONField | Dados de precificação |
| `commit_token` | CharField(64, null) | Chave de idempotência |

**Propriedade `items`:** Getter/setter que gerencia SessionItems com cache.

### SessionItem

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `session` | FK(Session) | Sessão |
| `line_id` | CharField(64) | ID da linha (auto "L-XXXXXXXX") |
| `sku` | CharField(64) | SKU do produto |
| `name` | CharField(200) | Nome do produto |
| `qty` | DecimalField(12,3) | Quantidade |
| `unit_price_q` | BigIntegerField | Preço unitário (centavos) |
| `line_total_q` | BigIntegerField | Total da linha (centavos) |
| `meta` | JSONField | Metadados |

### Order

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | CharField(64, unique) | Referência do pedido (auto "ORD-YYYYMMDD-XXXXXXXX") |
| `channel` | FK(Channel) | Canal de origem |
| `status` | CharField | NEW, CONFIRMED, PROCESSING, READY, DISPATCHED, DELIVERED, COMPLETED, CANCELLED, RETURNED |
| `snapshot` | JSONField | Estado congelado da sessão no commit |
| `data` | JSONField | customer, fulfillment, delivery, payment |
| `total_q` | BigIntegerField | Total em centavos |
| `created_at` | DateTimeField | Criação |
| `confirmed_at` ... `returned_at` | DateTimeField | Timestamps por status |

**Máquina de estados:** Configurável via `channel.config["status_flow"]` com transições e timestamps automáticos.

**Métodos:**
- `transition_status(new_status, actor)` — Transição atômica com validação
- `emit_event(event_type, actor, payload)` — Cria OrderEvent

### OrderItem

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `order` | FK(Order) | Pedido |
| `line_id` | CharField(64) | ID da linha |
| `sku` | CharField(64) | SKU |
| `qty` | DecimalField(12,3) | Quantidade |
| `unit_price_q` | BigIntegerField | Preço unitário (centavos) |
| `line_total_q` | BigIntegerField | Total da linha (centavos) |

### OrderEvent

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `order` | FK(Order) | Pedido |
| `seq` | PositiveIntegerField | Sequência monotônica |
| `type` | CharField(64) | Tipo (ex: "status_changed", "created") |
| `actor` | CharField(128) | Quem (ex: "system", "user:joao") |
| `payload` | JSONField | Dados do evento |

### Directive

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `topic` | CharField(64) | Tópico (ex: "stock.hold", "notification.send") |
| `status` | CharField | "queued", "running", "done", "failed" |
| `payload` | JSONField | Dados da directive |
| `attempts` | IntegerField | Tentativas |
| `available_at` | DateTimeField | Quando executar |
| `last_error` | TextField | Último erro |

### Fulfillment

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `order` | FK(Order) | Pedido |
| `status` | CharField | PENDING, IN_PROGRESS, SHIPPED, DELIVERED, CANCELLED |
| `tracking_code` | CharField(128) | Código de rastreio |
| `carrier` | CharField(64) | Transportadora |
| `meta` | JSONField | Dados extras |

## Serviços

### ModifyService

Aplica operações atômicas na sessão.

```python
from shopman.ordering.services.modify import ModifyService

session = ModifyService.modify_session(
    session_key="SESS-abc123",
    channel_ref="whatsapp",
    ops=[
        {"op": "add_line", "sku": "CROISSANT", "qty": "3"},
        {"op": "add_line", "sku": "CAFE-ESPRESSO", "qty": "1"},
        {"op": "set_data", "path": "customer.name", "value": "Maria"},
    ],
)
```

**Operações suportadas:**
- `add_line` — Adicionar item (`sku`, `qty`)
- `remove_line` — Remover item (`line_id`)
- `set_qty` — Alterar quantidade (`line_id`, `qty`)
- `replace_sku` — Trocar SKU (`line_id`, `sku`)
- `set_data` — Definir dados (`path`, `value`)
- `merge_lines` — Mesclar linhas com mesmo SKU (`line_id`, `into_line_id`)

### CommitService

Converte sessão em pedido atomicamente.

```python
from shopman.ordering.services.commit import CommitService

result = CommitService.commit(
    session_key="SESS-abc123",
    channel_ref="whatsapp",
    idempotency_key="commit:whatsapp:unique-key",
)
# {"order_ref": "ORD-20260322-abc12345", "order_id": 42, "status": "committed", "total_q": 3340}
```

Pipeline do commit:
1. Adquire lock de idempotência
2. Valida estado da sessão (open, não vazia)
3. Verifica checks obrigatórios (freshness via rev)
4. Verifica holds não expirados
5. Verifica issues não bloqueantes
6. Executa validators (stage="commit")
7. Cria Order + OrderItems
8. Emite evento "created"
9. Marca sessão como committed
10. Enfileira post_commit_directives

### SessionWriteService

Aplica resultados de checks assíncronos.

```python
from shopman.ordering.services.write import SessionWriteService

SessionWriteService.apply_check_result(
    session_key="SESS-abc123",
    channel_ref="whatsapp",
    expected_rev=3,
    check_code="stock",
    check_payload={"holds": [...]},
    issues=[{"source": "stock", "severity": "warning", "message": "..."}],
)
```

### ResolveService

Resolve issues encontrados nos checks.

```python
from shopman.ordering.services.resolve import ResolveService

session = ResolveService.resolve(
    session_key="SESS-abc123",
    channel_ref="whatsapp",
    issue_id="issue-123",
    action_id="accept_alternative",
)
```

## Registry

Sistema de extensão baseado em protocols.

```python
from shopman.ordering.registry import (
    register_validator,
    register_modifier,
    register_directive_handler,
    register_issue_resolver,
)
```

### Validator
Valida sessão em stages ("draft", "commit", "import").

### Modifier
Transforma sessão (ex: precificação). Executa por `order` (menor primeiro).

### DirectiveHandler
Processa directives por topic. Deve ser idempotente.

### IssueResolver
Resolve issues por source (ex: "stock", "fraud").

## Protocols

### PaymentBackend

```python
class PaymentBackend(Protocol):
    def create_intent(self, amount_q, currency, reference=None) -> PaymentIntent: ...
    def authorize(self, intent_id, payment_method=None) -> CaptureResult: ...
    def capture(self, intent_id, amount_q=None) -> CaptureResult: ...
    def refund(self, intent_id, amount_q=None, reason=None) -> RefundResult: ...
    def cancel(self, intent_id) -> bool: ...
    def get_status(self, intent_id) -> PaymentStatus: ...
```

### FiscalBackend

```python
class FiscalBackend(Protocol):
    def emit(self, reference, items, customer=None, payment=None) -> FiscalDocumentResult: ...
    def query_status(self, reference) -> FiscalDocumentResult: ...
    def cancel(self, reference, reason) -> FiscalCancellationResult: ...
```

### AccountingBackend

```python
class AccountingBackend(Protocol):
    def get_cash_flow(self, start_date, end_date) -> CashFlowSummary: ...
    def get_accounts_summary(self, as_of=None) -> AccountsSummary: ...
    def create_payable(self, description, amount_q, due_date, ...) -> CreateEntryResult: ...
    def create_receivable(self, description, amount_q, due_date, ...) -> CreateEntryResult: ...
    def mark_as_paid(self, entry_id, ...) -> CreateEntryResult: ...
```

## Exceções

Todas herdam de `OrderError(code, message, context)`:

| Exceção | Uso |
|---------|-----|
| `ValidationError` | Validator falhou |
| `SessionError` | Problema na sessão (not_found, already_committed, locked) |
| `CommitError` | Commit falhou (blocking_issues, stale_checks, empty_session) |
| `DirectiveError` | Processamento de directive falhou |
| `IssueResolveError` | Resolução de issue falhou |
| `InvalidTransition` | Transição de status inválida |
| `IdempotencyCacheHit` | Controle de fluxo (resposta cacheada) |

## Convenções

- Valores monetários sempre em **centavos** (`_q` suffix), tipo `int`/`BigIntegerField`
- Quantidades em `Decimal` com 3 casas decimais
- Identificadores são `ref`, não `code` (exceção: `Product.sku`)
- Line IDs auto-gerados: `L-XXXXXXXX`
- Order refs: `ORD-YYYYMMDD-XXXXXXXX`
- Session keys: `SESS-XXXXXXXXXXXXXXXX`

## Exemplos

### Fluxo completo: sessão → pedido

```python
from shopman.ordering.services.modify import ModifyService
from shopman.ordering.services.commit import CommitService

# 1. Criar sessão e adicionar itens
session = ModifyService.modify_session(
    session_key="SESS-abc123",
    channel_ref="whatsapp",
    ops=[
        {"op": "add_line", "sku": "CROISSANT", "qty": "3"},
        {"op": "add_line", "sku": "CAFE-ESPRESSO", "qty": "1"},
        {"op": "set_data", "path": "customer.name", "value": "Maria"},
        {"op": "set_data", "path": "customer.phone", "value": "+5511999999999"},
    ],
)

# 2. Commit (cria pedido + enfileira directives)
result = CommitService.commit(
    session_key="SESS-abc123",
    channel_ref="whatsapp",
    idempotency_key="commit:whatsapp:unique-key",
)
# result["order_ref"] = "ORD-20260322-abc12345"

# 3. Directives enfileiradas automaticamente:
# - stock.hold (reserva estoque)
# - notification.send (notifica cliente)
# - confirmation.timeout (confirmação otimista)
```

### Transição de status

```python
from shopman.ordering.models import Order

order = Order.objects.get(ref="ORD-20260322-abc12345")

# Verificar transições permitidas
print(order.get_allowed_transitions())
# ["confirmed", "cancelled"]

# Transicionar
order.transition_status("confirmed", actor="system")
# → Atualiza confirmed_at, emite evento status_changed
```
