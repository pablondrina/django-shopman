# Guia — Lifecycle, Services, Adapters, Rules

> Como `shopman/` orquestra os 8 apps core para cenários de negócio concretos.

---

## Visão Geral

O módulo `shopman/` (em `framework/shopman/`) é o orquestrador do sistema. Ele não contém lógica de domínio — apenas **coordena** os apps core (Offerman, Stockman, Craftsman, Orderman, Guestman, Doorman, Payman) através de 4 conceitos separados:

1. **Lifecycle** (`lifecycle.py`) — **QUANDO**: dispatch config-driven via signal `order_changed`
2. **Services** (`services/`) — **O QUE**: lógica de negócio que chama Core services + adapters
3. **Adapters** (`adapters/`) — **COMO**: implementações swappable por provider (PIX, Stripe, ManyChat, etc.)
4. **Rules** (`rules/`) — **QUANTO/QUEM**: regras configuráveis via admin com RuleConfig no DB

```
shopman/
├── lifecycle.py        Signal → dispatch(order, phase) → services (config-driven)
├── production_lifecycle.py  Signal → dispatch_production(work_order, phase) → services
├── services/           services (availability, alternatives, stock, payment, customer, checkout, pricing, etc.)
├── adapters/           adapters (stock, payment_efi, payment_stripe, notification_*, etc.)
├── rules/              engine.py, pricing.py, validation.py
├── handlers/           directive handlers (notification, fulfillment, fiscal, loyalty, returns, etc.)
├── config.py           ChannelConfig dataclass (9 aspectos)
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

## Lifecycle — dispatch() Config-Driven

Não há Flow classes. Todo o comportamento é definido por `ChannelConfig` — lido do banco e resolvido por cascata (canal ← loja ← defaults). `dispatch()` é uma função pura.

### Como dispatch() Funciona

```
1. Core emite signal order_changed(order, event_type, actor)
   │
2. apps.py: on_order_changed_receiver
   ├── event_type="created"        → dispatch(order, "on_commit")
   └── event_type="status_changed" → dispatch(order, f"on_{order.status}")
   │
3. dispatch(order, phase) em lifecycle.py:
   ├── Resolve ChannelConfig.for_channel(order.channel_ref)
   ├── Lê payment.timing, fulfillment.timing, confirmation.mode, stock.check_on_commit
   └── Chama services apropriados para o phase + config
   │
4. Services chamam Core services e emitem Directives:
   └── services.stock.hold(order), services.payment.initiate(order), etc.
```

### Tabela Timing × Phase

| Config | Valor | Comportamento |
|--------|-------|---------------|
| `payment.timing` | `"external"` | Nenhum `payment.initiate` (caixa/marketplace) |
| `payment.timing` | `"at_commit"` | `payment.initiate` no commit |
| `payment.timing` | `"post_commit"` | `payment.initiate` no confirmed (padrão) |
| `fulfillment.timing` | `"at_commit"` | `fulfillment.create` no commit |
| `fulfillment.timing` | `"post_commit"` | `fulfillment.create` no ready (padrão) |
| `fulfillment.timing` | `"external"` | Nenhum `fulfillment.create` |
| `stock.check_on_commit` | `True` | Valida disponibilidade por item antes de hold (POS) |
| `stock.check_on_commit` | `False` | Pula check (storefront valida durante checkout) |
| `confirmation.mode` | `"immediate"` | Auto-confirma no commit |
| `confirmation.mode` | `"optimistic"` | Auto-confirma após timeout se não cancelado |
| `confirmation.mode` | `"manual"` | Aguarda aprovação explícita do operador |

### Lifecycle Customizável por Canal

O campo `ChannelConfig.lifecycle` permite sobrescrever as transições e status terminais de um canal:

```python
# Channel.config (Admin)
{
    "lifecycle": {
        "transitions": {
            "new": ["confirmed", "cancelled"],
            "confirmed": ["ready", "cancelled"]
        },
        "terminal_statuses": ["ready", "cancelled"]
    }
}
```

Esses valores são baked no `order.snapshot["lifecycle"]` no momento do commit, garantindo que o lifecycle do pedido não muda se a config mudar depois.

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
| `loyalty` | earn | Directive (async) | Async |
| `fiscal` | emit, cancel | Directive (async) | Async |

### Sync vs Async

Services sync (stock, payment, customer) executam diretamente. Services async (notification, loyalty, fiscal) criam `Directive` objects — o Core processa via `process_directives` command.

---

## Adapters — Implementações Swappable

Adapters implementam protocolos definidos em `protocols.py`. Trocar provider = mudar uma linha em settings.py.

### Resolução

```python
from shopman.adapters import get_adapter

adapter = get_adapter("payment", method="pix")  # → payment_efi module
adapter = get_adapter("notification")            # → notification_manychat (default)
adapter = get_adapter("stock")                   # → shopman.adapters.stock
```

---

## Rules — Regras Configuráveis via Admin

Rules são regras de negócio configuráveis pelo operador via admin (modelo `RuleConfig`).

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

Cada canal de venda é configurado por um `ChannelConfig` dataclass com 9 aspectos. Documentação completa das chaves em [`data-schemas.md`](../reference/data-schemas.md).

### Cascata de Configuração

```
Channel.config  ←  Shop.defaults  ←  ChannelConfig.defaults()
  (específico)      (global loja)      (hardcoded)
```

### 9 Aspectos

| Aspecto | Pergunta respondida |
|---------|---------------------|
| `confirmation` | Como o pedido é aceito? (immediate / optimistic / manual) |
| `payment` | Como e quando o cliente paga? (method, timing) |
| `fulfillment` | Quando criar fulfillment? (at_commit / post_commit / external) |
| `stock` | Comportamento de reserva de estoque (hold_ttl, check_on_commit) |
| `notifications` | Por onde avisar? (backend, fallback_chain) |
| `pricing` | Como o preço é definido? (internal / external) |
| `editing` | Itens podem ser editados? (open / locked) |
| `rules` | Quais validators/modifiers ativar? |
| `lifecycle` | Transições e status terminais customizados por canal |

---

## Handlers (Directives assíncronas)

| Handler | Topic | Ação |
|---------|-------|------|
| `NotificationSendHandler` | `notification.send` | Envia notificação |
| `ConfirmationTimeoutHandler` | `confirmation.timeout` | Auto-confirma após timeout |
| `CustomerEnsureHandler` | `customer.ensure` | Garante customer existe |
| `NFCeEmitHandler` | `fiscal.emit_nfce` | Emite NFC-e |
| `NFCeCancelHandler` | `fiscal.cancel_nfce` | Cancela NFC-e |
| `ReturnHandler` | `return.process` | Processa devolução |
| `FulfillmentCreateHandler` | `fulfillment.create` | Cria fulfillment |
| `FulfillmentUpdateHandler` | `fulfillment.update` | Atualiza fulfillment |
| `LoyaltyEarnHandler` | `loyalty.earn` | Registra pontos de fidelidade |

---

## Pendências Conhecidas

- **BusinessHoursRule**: Seta flag `outside_business_hours` mas NÃO bloqueia checkout. Fluxo completo de encomendas/horário pendente de revisão dedicada.
- **Pipeline audit**: Guards, transições e edge cases a revisar após estabilização.
