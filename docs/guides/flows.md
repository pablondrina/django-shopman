# Guia — Flows, Services, Adapters, Rules

> Como `shopman/` orquestra os 8 apps core para cenários de negócio concretos.

---

## Visão Geral

O módulo `shopman/` (em `framework/shopman/`) é o orquestrador do sistema. Ele não contém lógica de domínio — apenas **coordena** os apps core (Offerman, Stockman, Craftsman, Omniman, Guestman, Doorman, Payman) através de 4 conceitos separados:

1. **Flows** (`flows.py`) — **QUANDO**: coordenação de lifecycle via herança Python
2. **Services** (`services/`) — **O QUE**: lógica de negócio que chama Core services + adapters
3. **Adapters** (`adapters/`) — **COMO**: implementações swappable por provider (PIX, Stripe, ManyChat, etc.)
4. **Rules** (`rules/`) — **QUANTO/QUEM**: regras configuráveis via admin com RuleConfig no DB

```
shopman/
├── flows.py            Signal → dispatch() → Flow.on_<phase>() → services
├── services/           services (availability, alternatives, stock, payment, customer, checkout, pricing, etc.)
├── adapters/           adapters (stock, payment_efi, payment_stripe, notification_*, etc.)
├── rules/              engine.py, pricing.py, validation.py
├── handlers/           directive handlers (notification, fulfillment, fiscal, loyalty, returns, etc.)
├── backends/           backends remanescentes (notification_*, pricing, fiscal/accounting mock)
├── config.py           ChannelConfig dataclass (7 aspectos)
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

## Flows — Hierarquia de Lifecycle

Cada Flow class define as fases pelas quais um pedido passa. Services são chamados diretamente (sem indireção). O Flow é puro domínio.

### Hierarquia

```
BaseFlow                   # Ciclo completo — 10 fases, todo pedido
├── LocalFlow              # Presencial — confirmação imediata, sem pagamento digital
│   ├── PosFlow            # Balcão
│   └── TotemFlow          # Autoatendimento
├── RemoteFlow             # Remoto — pagamento obrigatório, notificação ativa
│   ├── WebFlow            # E-commerce
│   ├── WhatsAppFlow       # WhatsApp (via ManyChat)
│   └── ManychatFlow       # ManyChat genérico
└── MarketplaceFlow        # Marketplace — pagamento externo, confirmação pessimista
    └── IFoodFlow          # iFood
```

### 10 Fases do BaseFlow

| Fase | Trigger | Ações |
|------|---------|-------|
| `on_commit` | Order criada | `customer.ensure()`, `stock.hold()` (adopta holds da sessão), `handle_confirmation()` |
| `on_confirmed` | Status → CONFIRMED | `stock.fulfill()`, `payment.initiate()`, `notification.send("order_confirmed")` |
| `on_paid` | Webhook de pagamento | `notification.send("payment_confirmed")` (LocalFlow: no-op) |
| `on_processing` | Status → PROCESSING | `kds.dispatch()`, `notification.send("order_processing")` |
| `on_ready` | Status → READY | `fulfillment.create()`, `notification.send("order_ready")` |
| `on_dispatched` | Status → DISPATCHED | `notification.send("order_dispatched")` |
| `on_delivered` | Status → DELIVERED | `notification.send("order_delivered")` |
| `on_completed` | Status → COMPLETED | `loyalty.earn()`, `fiscal.emit()` |
| `on_cancelled` | Status → CANCELLED | `stock.release()`, `payment.refund()`, `notification.send("order_cancelled")` |
| `on_returned` | Status → RETURNED | `stock.revert()`, `payment.refund()`, `fiscal.cancel()`, `notification.send("order_returned")` |

### Como dispatch() Funciona

```
1. Core emite signal order_changed(order, event_type, actor)
   │
2. apps.py: on_order_changed handler
   ├── event_type="created"        → dispatch(order, "on_commit")
   └── event_type="status_changed" → dispatch(order, f"on_{order.status}")
   │
3. dispatch() em flows.py:
   ├── Lê channel.config["flow"] (ex: "web", "pos", "marketplace")
   ├── Busca Flow class no _registry (decorador @flow registra)
   └── Chama flow.on_<phase>(order)
   │
4. Flow method chama services:
   └── services.stock.hold(order), services.payment.initiate(order), etc.
```

### Overrides por Tipo de Canal

| Flow | on_commit | on_confirmed | on_paid |
|------|-----------|--------------|---------|
| **BaseFlow** | customer + stock.hold + confirmation | stock.fulfill + payment + notify | notify |
| **LocalFlow** | customer + stock.hold + loyalty + immediate confirm | stock.fulfill + notify (no payment) | no-op |
| **RemoteFlow** | (herda BaseFlow) | (herda BaseFlow) | (herda BaseFlow) |
| **MarketplaceFlow** | customer + stock.hold + reject if missing | stock.fulfill + notify (no payment) | notify |

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

### Princípio: Core Chamado, Nunca Contornado

Services DEVEM usar Core services. Se o Core diz `hold`, o app diz `hold`. Se o Core diz `fulfill`, o app diz `fulfill`.

```python
# Correto — usa Core service
from shopman.stocking.service import StockService
StockService(position).create_hold(sku, qty, session_key, ttl_minutes)

# Errado — acessa model diretamente
from shopman.stocking.models import Hold
Hold.objects.create(sku=sku, qty=qty, ...)
```

### Sync vs Async

Services sync (stock, payment, customer) executam diretamente — o resultado é necessário para responder ao cliente.

Services async (notification, loyalty, fiscal) criam `Directive` objects — o Core processa de forma assíncrona via `process_directives` command. O Flow NÃO decide se é sync ou async — chama services e pronto.

---

## Adapters — Implementações Swappable

Adapters implementam protocolos definidos em `protocols.py`. Trocar provider = mudar uma linha em settings.py.

### Mapeamento

```python
# settings.py
SHOPMAN_PAYMENT_ADAPTERS = {
    "pix": "shopman.adapters.payment_efi",
    "card": "shopman.adapters.payment_stripe",
    "counter": None,
    "external": None,
}

SHOPMAN_NOTIFICATION_ADAPTERS = {
    "manychat": "shopman.adapters.notification_manychat",
    "email": "shopman.adapters.notification_email",
    "console": "shopman.adapters.notification_console",
}

SHOPMAN_STOCK_ADAPTER = "shopman.adapters.stock"
```

### Resolução

```python
from shopman.adapters import get_adapter

adapter = get_adapter("payment", method="pix")  # → payment_efi module
adapter = get_adapter("notification")            # → notification_manychat (default)
adapter = get_adapter("stock")                   # → shopman.adapters.stock
```

O `get_adapter()` resolve: channel override → settings global → default.

---

## Rules — Regras Configuráveis via Admin

Rules são regras de negócio configuráveis pelo operador via admin (modelo `RuleConfig`).

### Modelo RuleConfig

```python
class RuleConfig(models.Model):
    code       = CharField(max_length=80, unique=True)   # "d1_discount", "happy_hour"
    rule_path  = CharField(max_length=200)               # "shopman.rules.pricing.D1Discount"
    label      = CharField(max_length=120)               # "Desconto D-1"
    enabled    = BooleanField(default=True)               # Toggle on/off
    params     = JSONField(default=dict)                  # {"percent": 30}
    channels   = ManyToManyField(Channel, blank=True)     # Filtro por canal
    priority   = IntegerField(default=0)                  # Ordem de execução
```

### Engine

O `rules.engine` carrega, cacheia e registra rules ativas:

1. `get_active_rules(channel, stage)` — retorna RuleConfigs ativos (com cache de 1h)
2. `load_rule(rule_config)` — importa e instancia a classe, passando `params` como kwargs
3. `register_active_rules()` — chamado no boot (`apps.py`), registra validators no Core Registry

Cache invalidado automaticamente no `post_save` de `RuleConfig`.

### Rules Disponíveis

#### Pricing (modifiers)

| Code | Classe | Params | Descrição |
|------|--------|--------|-----------|
| `d1_discount` | `D1Discount` | `percent: int` | Desconto para produtos D-1 (sobras do dia anterior) |
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

Cada canal de venda é configurado por um `ChannelConfig` dataclass com 7 aspectos. Documentação completa das chaves em [`data-schemas.md`](../reference/data-schemas.md).

### Cascata de Configuração

```
Channel.config  ←  Shop.defaults  ←  ChannelConfig.defaults()
  (específico)      (global loja)      (hardcoded)
```

### Configuração Flat (novo estilo)

```python
channel.config = {
    "flow": "web",                         # qual Flow class usar
    "confirmation_mode": "optimistic",     # immediate | optimistic | pessimistic
    "confirmation_timeout": 300,           # segundos
    "payment": ["pix", "card"],            # métodos aceitos
    "stock_hold_ttl": 30,                  # minutos
    "notification_adapter": "manychat",    # adapter primário
    "notification_fallback": ["email"],    # fallback chain
    "listing_ref": "cardapio-web",         # qual catálogo
}
```

---

## Exemplo Concreto: Pedido Web

Fluxo completo de um pedido no storefront web:

```
1. Cliente navega no catálogo
   └── web/views/catalog.py → Offering service (listings, collections)

2. Cliente adiciona ao carrinho
   └── web/views/cart.py → CartService (session-based)
   └── services.availability.reserve(sku, qty, session_key=...) — sync, inline
       ├── ok=True → cria hold tagged com session_key (Stockman)
       └── ok=False → CartUnavailableError (com alternatives)
   └── ModifyService.modify_session(...) atualiza Session.snapshot

3. Cliente faz checkout
   └── web/views/checkout.py → services.checkout.process()
   └── CommitService._do_commit() cria Order + snapshot
   └── Signal order_changed(event_type="created")
   └── dispatch(order, "on_commit")
   └── WebFlow.on_commit():
       ├── customer.ensure(order)      → CustomerService
       ├── stock.hold(order)           → adopta holds da sessão (re-tag para `order:<ref>`)
       └── handle_confirmation()       → optimistic → Directive(confirmation.timeout)
       └── order.transition_status(CONFIRMED)

4. Signal order_changed(event_type="status_changed", status=CONFIRMED)
   └── dispatch(order, "on_confirmed")
   └── WebFlow.on_confirmed():
       ├── payment.initiate(order)     → adapter → PIX QR code gerado
       └── notification.send(order, "order_confirmed")

5. Cliente paga (PIX callback via webhook)
   └── webhooks/efi.py → payment confirmed
   └── dispatch(order, "on_paid")
   └── WebFlow.on_paid():
       └── notification.send(order, "payment_confirmed")
   (stock.fulfill já ocorreu em on_confirmed)

6. Operador inicia preparo → status PROCESSING
   └── dispatch(order, "on_processing")
   └── kds.dispatch(order)             → KDS tickets criados

7. Todos tickets KDS prontos → status READY
   └── dispatch(order, "on_ready")
   └── fulfillment.create(order)

8. Entrega → status DELIVERED → COMPLETED
   └── dispatch(order, "on_completed")
   └── loyalty.earn(order) + fiscal.emit(order)
```

---

## Handlers (Directives assíncronas)

Handlers processam Directives criadas por services. Stock e payment NÃO usam mais directives — são chamados sync via services + adapters.

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
| `CheckoutInferDefaultsHandler` | `checkout.infer_defaults` | Infere preferências do checkout |
| `StockIssueResolver` | (signal `stock_issue`) | Resolve alertas de stock |

---

## Signal Receivers

| Receiver | Signal | Ação |
|----------|--------|------|
| `on_holds_materialized` | `holds_materialized` (Stockman) | Auto-commit de sessões aguardando produção |
| `on_production_voided` | `production_changed` (Craftsman) | Libera demand holds quando produção anulada |

---

## Pendências Conhecidas

- **BusinessHoursRule**: Seta flag `outside_business_hours` mas NÃO bloqueia checkout. Fluxo completo de encomendas/horário pendente de revisão dedicada.
- **Gestor de Pedidos**: Avaliar migração para Admin/Unfold ou redesign de UX.
- **Pipeline audit**: Guards, transições e edge cases a revisar após estabilização.
