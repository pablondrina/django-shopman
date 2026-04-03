# Guia — Channels (Orquestrador)

> Como `channels/` conecta os 8 apps core para cenários de negócio concretos.

---

## Visão Geral

O módulo `channels/` (em `shopman-app/channels/`) é o orquestrador do sistema. Ele não contém lógica de domínio — apenas **conecta** os apps core (offering, stocking, crafting, ordering, customers, auth, payments) através de handlers, backends e um pipeline configurável por canal de venda.

```
channels/
├── config.py           ChannelConfig — 7 aspectos de configuração
├── presets.py           Presets prontos: pos(), remote(), marketplace()
├── topics.py            Constantes de tópicos de directives
├── hooks.py             Dispatcher: signal → pipeline → directives
├── setup.py             Registro centralizado (AppConfig.ready)
├── protocols.py         Contratos de backend (Stock, Customer, Notification, Pricing)
├── confirmation.py      Helpers de confirmação + cascata legada
├── notifications.py     Registry + dispatch de notificações
├── webhooks.py          Webhook Efi PIX
├── webhook_urls.py      URLs do webhook
├── handlers/            11 handlers (processam directives)
├── backends/            17 backends (adaptam core apps)
├── api/                 API REST (DRF)
└── web/                 Storefront (Django templates + HTMX)
```

---

## ChannelConfig — 7 Aspectos

Cada canal de venda é configurado por um `ChannelConfig` dataclass com 7 aspectos. Cada aspecto responde a UMA pergunta sobre o comportamento do canal.

### 1. Confirmation — Como o pedido é aceito?

```python
@dataclass
class Confirmation:
    mode: str = "immediate"
    # "immediate"  — auto-confirma na criação
    # "optimistic" — auto-confirma após timeout se operador não cancela
    # "manual"     — aguarda aprovação explícita do operador
    timeout_minutes: int = 5  # só para mode=optimistic
```

### 2. Payment — Como o cliente paga?

```python
@dataclass
class Payment:
    method: str = "counter"
    # "counter"  — no caixa/entrega
    # "pix"      — PIX com QR code
    # "external" — já pago (marketplace)
    timeout_minutes: int = 15  # só para method=pix
```

### 3. Stock — Comportamento de reserva de estoque

```python
@dataclass
class Stock:
    hold_ttl_minutes: int | None = None  # None = sem expiração
    safety_margin: int = 0
    planned_hold_ttl_hours: int = 48     # TTL para holds planejados
```

### 4. Pipeline — O que acontece em cada fase?

```python
@dataclass
class Pipeline:
    on_commit: list[str] = []           # Pedido criado
    on_confirmed: list[str] = []        # Confirmado
    on_processing: list[str] = []       # Em preparo
    on_ready: list[str] = []            # Pronto
    on_dispatched: list[str] = []       # Despachado
    on_delivered: list[str] = []        # Entregue
    on_completed: list[str] = []        # Completo
    on_cancelled: list[str] = []        # Cancelado
    on_returned: list[str] = []         # Devolvido
    on_payment_confirmed: list[str] = [] # Pagamento confirmado (webhook)
```

Cada fase é uma lista de **directive topics**. Notação `"topic:template"` para notificações com template.

### 5. Notifications — Por onde avisamos?

```python
@dataclass
class Notifications:
    backend: str = "manychat"
    # "manychat" | "sms" | "email" | "console" | "webhook" | "none"
    # Cadeia phone-first (Brasil): manychat (WhatsApp) → sms → email
    fallback_chain: list[str] = ["sms", "email"]
    routing: dict[str, str] | None = None  # evento → backend específico
```

### 6. Rules — Quais validators/modifiers ativar?

```python
@dataclass
class Rules:
    validators: list[str] = []   # ex: ["business_hours", "min_order"]
    modifiers: list[str] = []    # ex: ["shop.employee_discount", "shop.happy_hour"]
    checks: list[str] = []       # ex: ["stock"]
```

### 7. Flow — Como o pedido transita entre status?

```python
@dataclass
class Flow:
    transitions: dict[str, list[str]] | None = None
    terminal_statuses: list[str] | None = None
    auto_transitions: dict[str, str] | None = None
    auto_sync_fulfillment: bool = False
```

---

## Cascata de Configuração

A configuração efetiva de um canal é resolvida em cascata:

```
Channel.config  ←  Shop.defaults  ←  ChannelConfig.defaults()
  (específico)      (global loja)      (hardcoded)
```

- Chave **ausente** no override → herda do nível anterior
- Chave **presente** (mesmo `None`) → sobreescreve
- Dicts → merge recursivo
- Lists → sobreescreve (não concatena)

Implementação: `ChannelConfig.effective(channel)` em `config.py`.

---

## Presets

Presets são templates de `ChannelConfig` para cenários comuns. Retornam um dict pronto para `Channel.config`.

### `pos()` — Balcão

Operador presente, pagamento no caixa.

| Aspecto | Valor |
|---------|-------|
| Confirmação | `immediate` (auto-confirma) |
| Pagamento | `counter` (síncrono) |
| Stock | hold TTL 5 min |
| Pipeline on_commit | `customer.ensure` |
| Pipeline on_confirmed | `stock.commit`, `notification:order_confirmed` |
| Pipeline on_processing | `notification:order_processing` |
| Pipeline on_cancelled | `notification:order_cancelled` |
| Validators | `business_hours` |
| Modifiers | `shop.employee_discount` |

### `remote()` — E-commerce / WhatsApp

PIX assíncrono, confirmação otimista.

| Aspecto | Valor |
|---------|-------|
| Confirmação | `optimistic` (10 min timeout) |
| Pagamento | `pix` (15 min timeout) |
| Stock | hold 30 min, safety margin 10, planned hold 48h |
| Pipeline on_commit | `customer.ensure`, `stock.hold` |
| Pipeline on_confirmed | `pix.generate`, `notification:order_confirmed` |
| Pipeline on_payment_confirmed | `stock.commit`, `notification:payment_confirmed` |
| Pipeline on_processing | `notification:order_processing` |
| Pipeline on_ready | `fulfillment.create`, `notification:order_ready` |
| Pipeline on_dispatched | `notification:order_dispatched` |
| Pipeline on_delivered | `notification:order_delivered` |
| Pipeline on_cancelled | `stock.release`, `notification:order_cancelled` |
| Validators | `business_hours`, `min_order` |
| Modifiers | `shop.happy_hour` |
| Checks | `stock` |
| Flow | `auto_sync_fulfillment = True` |

### `marketplace()` — iFood / Rappi

Já pago e confirmado pelo marketplace.

| Aspecto | Valor |
|---------|-------|
| Confirmação | `immediate` (marketplace já confirmou) |
| Pagamento | `external` (marketplace já cobrou) |
| Pipeline on_commit | `customer.ensure` |
| Pipeline on_confirmed | `stock.commit` |
| Notifications | `none` (marketplace notifica o cliente) |
| Validators | `[]` (desativados) |
| Modifiers | `[]` (desativados) |

---

## Lifecycle — Signal → Pipeline → Directives

O ciclo de vida de um pedido funciona assim:

```
1. Session criada (modify_session)
   │
2. Modifiers rodam (pricing, promoções, cupons)
   │
3. Validators de draft rodam
   │
4. Commit (commit_session)
   │
   ├── Validators de commit rodam
   ├── Order criada com snapshot
   ├── order_changed signal (event_type="created")
   │     └── hooks.on_order_lifecycle()
   │           ├── mode=immediate → auto-confirma → order_changed (status_changed)
   │           ├── mode=optimistic → directive: confirmation.timeout
   │           └── mode=manual → aguarda operador
   │
   ├── pipeline.on_commit executado:
   │     ├── customer.ensure → CustomerEnsureHandler
   │     ├── stock.hold → StockHoldHandler
   │     └── ...
   │
5. Status muda → order_changed (event_type="status_changed")
   │     └── hooks.on_order_lifecycle() lê pipeline do novo status
   │           └── Cria directives conforme configuração
   │
6. Pagamento confirmado (webhook)
      └── hooks.on_payment_confirmed()
           └── pipeline.on_payment_confirmed executado
```

### Fluxo no código

1. `order_changed` signal → `hooks.on_order_lifecycle()` (conectado em `ChannelsConfig.ready()`)
2. Hook lê `ChannelConfig.effective(channel).pipeline`
3. Para cada topic no pipeline da fase atual, cria uma `Directive`
4. `Directive.post_save` signal → `ordering.dispatch` auto-despacha para o handler registrado
5. Handler processa a directive (ex: `StockHoldHandler.handle()` cria hold via `StockBackend`)

---

## Handlers

Handlers processam directives. Cada handler é registrado em `setup.py` via `registry.register_directive_handler()`.

| Handler | Topic | Backend | Ação |
|---------|-------|---------|------|
| `StockHoldHandler` | `stock.hold` | `StockBackend` | Cria reserva de estoque |
| `StockCommitHandler` | `stock.commit` | `StockBackend` | Confirma reserva |
| `PixGenerateHandler` | `pix.generate` | `PaymentBackend` | Gera QR code PIX |
| `PixTimeoutHandler` | `pix.timeout` | `PaymentBackend` | Trata timeout de PIX |
| `PaymentCaptureHandler` | `payment.capture` | `PaymentBackend` | Captura pagamento |
| `PaymentRefundHandler` | `payment.refund` | `PaymentBackend` | Processa reembolso |
| `NotificationSendHandler` | `notification.send` | `NotificationBackend` | Envia notificação |
| `ConfirmationTimeoutHandler` | `confirmation.timeout` | — | Auto-confirma após timeout |
| `CustomerEnsureHandler` | `customer.ensure` | `CustomerBackend` | Garante customer existe |
| `NFCeEmitHandler` | `fiscal.emit_nfce` | `FiscalBackend` | Emite NFC-e |
| `NFCeCancelHandler` | `fiscal.cancel_nfce` | `FiscalBackend` | Cancela NFC-e |
| `PurchaseToPayableHandler` | `accounting.create_payable` | `AccountingBackend` | Cria contas a pagar |
| `ReturnHandler` | `return.process` | Stock+Payment+Fiscal | Processa devolução |
| `FulfillmentCreateHandler` | `fulfillment.create` | — | Cria fulfillment |
| `FulfillmentUpdateHandler` | `fulfillment.update` | — | Atualiza fulfillment |

### Signal Receivers (não são handlers de directive)

| Receiver | Signal | Ação |
|----------|--------|------|
| `on_holds_materialized` | `holds_materialized` (stocking) | Auto-commit de sessões aguardando produção |
| `on_production_voided` | `production_changed` (crafting) | Libera demand holds quando produção é anulada |

---

## Backends

Backends adaptam os core apps aos protocols definidos em `protocols.py`.

| Backend | Protocol | Core App |
|---------|----------|----------|
| `StockingBackend` | `StockBackend` | `shopman.stocking` |
| `NoopStockBackend` | `StockBackend` | — (fallback) |
| `MockPaymentBackend` | `PaymentBackend` | — (dev/test) |
| `EfiPixBackend` | `PaymentBackend` | `shopman.payments` + API Efi |
| `StripeBackend` | `PaymentBackend` | `shopman.payments` + API Stripe |
| `MockFiscalBackend` | `FiscalBackend` | — (dev/test) |
| `FocusBackend` | `FiscalBackend` | API Focus NF-e |
| `MockAccountingBackend` | `AccountingBackend` | — (dev/test) |
| `ContaazulBackend` | `AccountingBackend` | API Conta Azul |
| `CustomersBackend` | `CustomerBackend` | `shopman.customers` |
| `ConsoleBackend` | `NotificationBackend` | — (stdout) |
| `ManychatBackend` | `NotificationBackend` | API ManyChat |
| `EmailBackend` | `NotificationBackend` | Django email |
| `SmsBackend` | `NotificationBackend` | API SMS |
| `WebhookBackend` | `NotificationBackend` | HTTP webhook |
| `WhatsappBackend` | `NotificationBackend` | WhatsApp Cloud API |
| `OfferingBackend` | `PricingBackend` | `shopman.offering` |

---

## Modifiers e Validators

Registrados em `setup.py` via `registry.register_modifier()` e `registry.register_validator()`.

### Modifiers (ordem de execução)

| Ordem | Code | Origem | Descrição |
|-------|------|--------|-----------|
| 10 | `pricing.item` | `channels/handlers/pricing.py` | Preço base do backend (qty-aware) |
| 15 | `shop.d1_discount` | `shop/modifiers.py` | Desconto D-1 (sobras) |
| 20 | `shop.promotion` | `shop/modifiers.py` | Promoções automáticas |
| 25 | `shop.coupon` | `shop/modifiers.py` | Cupons de desconto |
| 50 | `pricing.session_total` | `channels/handlers/pricing.py` | Recalcula total da sessão |
| 60 | `shop.employee_discount` | `shop/modifiers.py` | Desconto funcionário (20%) |
| 65 | `shop.happy_hour` | `shop/modifiers.py` | Happy hour (10%, 16h-18h) |

### Validators

| Code | Stage | Origem | Descrição |
|------|-------|--------|-----------|
| `shop.business_hours` | commit | `shop/validators.py` | Rejeita pedidos fora do horário (06h-20h) |
| `shop.minimum_order` | commit | `shop/validators.py` | Pedido mínimo para delivery (R$ 10,00) |
| `stock_check` | commit | `channels/setup.py` | Valida stock check antes do commit |

### Checks

| Code | Origem | Descrição |
|------|--------|-----------|
| `stock` | `channels/handlers/stock.py` | Verifica disponibilidade de estoque |

Modifiers e validators são **filtrados por canal** via `ChannelConfig.rules`. Apenas os listados em `rules.validators` e `rules.modifiers` são executados para aquele canal.

---

## Registro Centralizado — setup.py

Tudo é registrado em `setup.register_all()`, chamado por `ChannelsConfig.ready()`:

1. Stock handlers + backend (auto-detecção ou `SHOPMAN_STOCK_BACKEND`)
2. Payment handlers + backend (`SHOPMAN_PAYMENT_BACKEND`)
3. Notification handler + backends (console + manychat se configurado)
4. Confirmation handler
5. Customer handler
6. Fiscal handlers + backend (`SHOPMAN_FISCAL_BACKEND`)
7. Accounting handler + backend (`SHOPMAN_ACCOUNTING_BACKEND`)
8. Return handler (stock + payment + fiscal)
9. Fulfillment handlers
10. Pricing modifiers (item + session total + shop modifiers)
11. Stock check
12. Stock validator
13. Stock signals (`holds_materialized`, `production_changed`)

---

## Como Criar um Novo Canal

1. Escolha um preset base ou crie um `ChannelConfig` customizado:

```python
from shopman.ordering.models import Channel
from channels.presets import remote

channel = Channel.objects.create(
    ref="whatsapp-delivery",
    name="WhatsApp Delivery",
    config=remote(),
)
```

2. Customize aspectos específicos:

```python
config = remote()
config["pipeline"]["on_ready"].append("fiscal.emit_nfce")
config["rules"]["validators"].append("min_order")
config["notifications"]["backend"] = "whatsapp"

channel = Channel.objects.create(
    ref="whatsapp-delivery",
    name="WhatsApp Delivery",
    config=config,
)
```

---

## Como Adicionar um Handler Customizado

1. Defina o topic em `topics.py`:

```python
MY_CUSTOM_TOPIC = "my_domain.action"
```

2. Crie o handler:

```python
class MyCustomHandler:
    topic = "my_domain.action"

    def handle(self, directive):
        payload = directive.payload
        # ... lógica de negócio
        directive.resolve(result={"status": "ok"})
```

3. Registre em `setup.py`:

```python
def _register_my_custom_handler() -> None:
    from channels.handlers.my_handler import MyCustomHandler
    registry.register_directive_handler(MyCustomHandler())
```

4. Adicione o topic ao pipeline do canal:

```python
config["pipeline"]["on_confirmed"].append("my_domain.action")
```

---

## Directive Topics — Referência

Constantes canônicas em `topics.py`:

| Constante | Valor |
|-----------|-------|
| `STOCK_HOLD` | `stock.hold` |
| `STOCK_COMMIT` | `stock.commit` |
| `STOCK_RELEASE` | `stock.release` |
| `PAYMENT_CAPTURE` | `payment.capture` |
| `PAYMENT_REFUND` | `payment.refund` |
| `PIX_GENERATE` | `pix.generate` |
| `PIX_TIMEOUT` | `pix.timeout` |
| `NOTIFICATION_SEND` | `notification.send` |
| `FULFILLMENT_CREATE` | `fulfillment.create` |
| `FULFILLMENT_UPDATE` | `fulfillment.update` |
| `CONFIRMATION_TIMEOUT` | `confirmation.timeout` |
| `CUSTOMER_ENSURE` | `customer.ensure` |
| `FISCAL_EMIT_NFCE` | `fiscal.emit_nfce` |
| `FISCAL_CANCEL_NFCE` | `fiscal.cancel_nfce` |
| `ACCOUNTING_CREATE_PAYABLE` | `accounting.create_payable` |
| `RETURN_PROCESS` | `return.process` |
