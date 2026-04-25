# Guia — Lifecycle, Services, Adapters, Rules

> Como `shopman/` orquestra os 8 apps core para cenários de negócio concretos.

---

## Visão Geral

O módulo `shopman/` (em `shopman/shop/`) é o orquestrador do sistema. Ele não contém lógica de domínio — apenas **coordena** os apps core (Offerman, Stockman, Craftsman, Orderman, Guestman, Doorman, Payman) através de 4 conceitos separados:

1. **Lifecycle** (`lifecycle.py`) — **QUANDO**: coordenação config-driven via `dispatch(order, phase)`
2. **Services** (`services/`) — **O QUE**: lógica de negócio que chama Core services + adapters
3. **Adapters** (`adapters/`) — **COMO**: implementações swappable por provider (PIX, Stripe, ManyChat, etc.)
4. **Rules** (`rules/`) — **QUANTO/QUEM**: regras configuráveis via admin com RuleConfig no DB

```
shopman/
├── lifecycle.py        Signal → dispatch(order, phase) → services (config-driven)
├── production_lifecycle.py  Signal → dispatch_production(work_order, phase)
├── services/           services (availability, alternatives, stock, payment, customer, checkout, pricing, etc.)
├── adapters/           adapters (stock, payment_efi, payment_stripe, notification_*, etc.)
├── rules/              engine.py, pricing.py, validation.py
├── handlers/           directive handlers (notification, fulfillment, fiscal, loyalty, returns, etc.)
├── config.py           ChannelConfig dataclass (8 aspectos)
├── setup.py            register_all() — registro centralizado de handlers
├── protocols.py        Contratos de backend (Stock, Customer, Notification, Pricing)
├── topics.py           Constantes de tópicos de directives
├── notifications.py    Registry + dispatch de notificações
├── confirmation.py     Helpers de confirmação
├── modifiers.py        D1, Discount, Employee, HappyHour modifiers
├── webhooks/           efi.py, stripe.py
├── admin/              Unfold admin (shop, orders, alerts, kds, closing, rules, dashboard)
├── web/                Storefront (Django templates + HTMX)
├── api/                API REST (DRF)
└── apps.py             Signal wiring + handler registration + rules boot
```

---

## Lifecycle — Dispatch Config-Driven

O comportamento de cada canal é 100% configurado via `ChannelConfig` — sem classes de Flow ou herança Python. `dispatch()` lê o config e chama os services corretos para cada fase.

### Como dispatch() Funciona

```
1. Core emite signal order_changed(order, event_type, actor)
   │
2. apps.py: on_order_changed handler
   ├── event_type="created"        → dispatch(order, "on_commit")
   └── event_type="status_changed" → dispatch(order, f"on_{order.status}")
   │
3. dispatch() em lifecycle.py:
   ├── config = ChannelConfig.for_channel(order.channel_ref)
   └── Chama phase handler: _on_commit(order, config), _on_confirmed(order, config), etc.
   │
4. Phase handler chama services baseado em config:
   ├── config.payment.timing == "at_commit" → payment.initiate(order)
   ├── config.fulfillment.timing == "post_commit" → fulfillment.create(order)
   ├── config.confirmation.mode == "immediate" → order.transition_status(CONFIRMED)
   └── config.stock.check_on_commit → availability.check() por SKU
```

### Timing × Phase Table

| Aspecto | Valor | Fase |
|---------|-------|------|
| `payment.timing` | `"external"` | nenhum payment.initiate |
| `payment.timing` | `"at_commit"` | payment.initiate em on_commit |
| `payment.timing` | `"post_commit"` | payment.initiate em on_confirmed (padrão) |
| `fulfillment.timing` | `"at_commit"` | fulfillment.create em on_commit |
| `fulfillment.timing` | `"post_commit"` | fulfillment.create em on_ready (padrão) |
| `fulfillment.timing` | `"external"` | nenhum fulfillment.create |
| `confirmation.mode` | `"immediate"` | auto-confirm em on_commit |
| `confirmation.mode` | `"auto_confirm"` | auto-confirm após timeout se operador não cancelar |
| `confirmation.mode` | `"auto_cancel"` | auto-cancel após timeout se operador não confirmar |
| `confirmation.mode` | `"manual"` | aguarda operador, sem timeout |
| `stock.check_on_commit` | `True` | per-item check antes do hold (POS, marketplace) |

### 10 Fases

| Fase | Trigger | Ações |
|------|---------|-------|
| `on_commit` | Order criada | `customer.ensure()`, `stock.hold()`, `loyalty.redeem()`, `handle_confirmation()` |
| (guard) | Antes de CONFIRMED | `ensure_confirmable()` — exige `availability_decision.approved == True` em `order.data`. Sem decisão positiva, `InvalidTransition("availability_not_approved")`. Exceção: canais com `payment.timing == "external"` (marketplace). Ver §Availability Approval abaixo |
| `on_confirmed` | Status → CONFIRMED | `payment.initiate()` (se post_commit), `stock.fulfill()` (se counter), `notification.send` |
| `on_paid` | Webhook de pagamento | `stock.fulfill()`, `notification.send("payment_confirmed")` |
| `on_preparing` | Status → PREPARING | `kds.dispatch()`, `notification.send` |
| `on_ready` | Status → READY | `fulfillment.create()` (se post_commit), `notification.send` |
| `on_dispatched` | Status → DISPATCHED | `notification.send` |
| `on_delivered` | Status → DELIVERED | `notification.send` |
| `on_completed` | Status → COMPLETED | `loyalty.earn()`, `fiscal.emit()` |
| `on_cancelled` | Status → CANCELLED | `kds.cancel_tickets()`, `stock.release()`, `payment.refund()`, `notification.send` |
| `on_returned` | Status → RETURNED | `stock.revert()`, `payment.refund()`, `fiscal.cancel()`, `notification.send` |

### Availability Approval (Guard de Confirmação)

Antes de transitar para CONFIRMED, todo pedido deve ter uma decisão positiva de disponibilidade em `order.data["availability_decision"]`. Isso é enforced por `ensure_confirmable()` em `lifecycle.py`.

**Fluxo:**

1. Pedido criado (status NEW) — operador vê na fila
2. Operador avalia disponibilidade dos itens (via Gestor Pedidos)
3. Três ações possíveis:
   - `approve_order(order)` — aprova integralmente (`approved: True`)
   - `approve_with_adjustments(order, decisions)` — aprova com ajustes de quantidade por SKU
   - `reject_order(order)` — rejeita (`approved: False`, cancela o pedido)
4. Ao aprovar, `_record_availability_decision()` grava em `order.data["availability_decision"]`
5. `ensure_confirmable()` verifica: sem decisão positiva → `InvalidTransition("availability_not_approved")`

**Exceção:** canais com `payment.timing == "external"` (marketplace como iFood) pulam esse guard — o marketplace gerencia sua própria confirmação.

**Schema** de `availability_decision`:
```json
{
  "approved": true,
  "decisions": [{"sku": "PAO-001", "original_qty": 5, "approved_qty": 3, "action": "adjusted"}],
  "decided_at": "2026-04-24T10:00:00Z",
  "decided_by": "operator_username"
}
```

---

## Services — Lógica de Negócio

Cada service encapsula uma preocupação de negócio. Services chamam Core services (StockService, PaymentService, CatalogService, etc.) e adapters.

### Inventário

| Service | Métodos | Core Service | Natureza |
|---------|---------|--------------|----------|
| `availability` | check, reserve | Stockman.availability + adapter `stock.create_hold` | Sync |
| `alternatives` | find | Offerman/Stockman | Sync |
| `stock` | hold, fulfill, release, revert | adapter `stock` (adopta holds da sessão em `hold`) | Sync |
| `payment` | initiate, capture, refund | PaymentService via adapter | Sync |
| `customer` | ensure | CustomerService | Sync |
| `checkout` | process | CommitService, ModifyService | Sync |
| `checkout_defaults` | infer | PreferenceService | Sync |
| `pricing` | resolve | CatalogService.price() + Rules | Sync |
| `cancellation` | cancel | Order.transition_status() | Sync |
| `kds` | dispatch, on_all_tickets_done | KDSInstance, KDSTicket models | Sync |
| `fulfillment` | create, update | Fulfillment model | Sync |
| `notification` | send | Directive (async) | Async |
| `loyalty` | earn, redeem | Directive (async) | Async |
| `fiscal` | emit, cancel | Directive (async) | Async |

---

## Adapters — Implementações Swappable

Adapters implementam protocolos definidos em `protocols.py`. Trocar provider = mudar uma linha em settings.py.

```python
from shopman.adapters import get_adapter

adapter = get_adapter("payment", method="pix")  # → payment_efi module
adapter = get_adapter("notification")            # → notification_manychat (default)
adapter = get_adapter("stock")                   # → shopman.adapters.stock
```

---

## Rules — Regras Configuráveis via Admin

Rules são regras de negócio configuráveis pelo operador via admin (`RuleConfig` model).

### Rules Disponíveis

#### Pricing (modifiers)

| Code | Classe | Params | Descrição |
|------|--------|--------|-----------|
| `d1_discount` | `D1Discount` | `percent: int` | Desconto para produtos D-1 |
| `promotion` | `PromotionDiscount` | — | Promoções automáticas do admin |
| `employee_discount` | `EmployeeDiscount` | `percent: int` | Desconto para funcionários |
| `happy_hour` | `HappyHour` | `percent: int, start_hour, end_hour` | Desconto em horário específico |

#### Validation (validators)

| Code | Classe | Params | Descrição |
|------|--------|--------|-----------|
| `business_hours` | `BusinessHoursRule` | `open_hour, close_hour` | Seta flag `outside_business_hours` (NÃO bloqueia checkout) |
| `minimum_order` | `MinimumOrderRule` | `amount_q: int` | Bloqueia pedidos abaixo do valor mínimo |

---

## ChannelConfig — Configuração por Canal

Cada canal de venda é configurado por um `ChannelConfig` dataclass com 8 aspectos. Cascata: canal ← Shop.defaults ← hardcoded.

Ver: [`config.py`](../../shopman/shop/config.py) e [`data-schemas.md`](../reference/data-schemas.md).

---

## Handlers (Directives assíncronas)

Handlers processam Directives criadas por services. Note que nem tudo passa por
Directive: `customer.ensure`, `stock.hold`, `payment.initiate` e `fulfillment.create`
são chamadas **síncronas diretas** em lifecycle.py — não criam Directive. Apenas
operações que podem ser enfileiradas/retentadas usam o mecanismo de Directive.

| Handler | Topic | Ação |
|---------|-------|------|
| `NotificationSendHandler` | `notification.send` | Envia notificação via adapter |
| `ConfirmationTimeoutHandler` | `confirmation.timeout` | Auto-confirma (auto_confirm) ou auto-cancela (auto_cancel) após timeout |
| `NFCeEmitHandler` | `fiscal.emit_nfce` | Emite NFC-e |
| `NFCeCancelHandler` | `fiscal.cancel_nfce` | Cancela NFC-e |
| `ReturnHandler` | `return.process` | Processa devolução |
| `LoyaltyEarnHandler` | `loyalty.earn` | Registra pontos de fidelidade |
