# Arquitetura — Django Shopman

## Visão Geral

Django Shopman é composto por **8 apps core** independentes e um **orquestrador** (`channels/`) que os conecta para cenários de negócio concretos. Cada app core é um pacote pip instalável separadamente.

## Diagrama de Camadas

```
┌──────────────────────────────────────────────────────────────────────┐
│                         PROJETO DJANGO                               │
│                     (shopman-app/project/)                            │
│                   settings.py · urls.py · wsgi                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              SHOP (shopman-app/shop/)                        │    │
│  │         Shop (singleton), Promotion, Coupon                  │    │
│  │         Configuração global + defaults de canal              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │            CHANNELS — Orquestrador (shopman-app/channels/)   │    │
│  │                                                              │    │
│  │  config.py   presets.py   topics.py   hooks.py   setup.py   │    │
│  │                                                              │    │
│  │  handlers/                    backends/                      │    │
│  │  ├── stock.py                 ├── stock.py                   │    │
│  │  ├── payment.py               ├── payment_mock.py            │    │
│  │  ├── notification.py          ├── payment_efi.py             │    │
│  │  ├── confirmation.py          ├── payment_stripe.py          │    │
│  │  ├── customer.py              ├── notification_*.py          │    │
│  │  ├── fiscal.py                ├── customer.py                │    │
│  │  ├── accounting.py            ├── pricing.py                 │    │
│  │  ├── returns.py               ├── fiscal_*.py                │    │
│  │  ├── fulfillment.py           └── accounting_*.py            │    │
│  │  ├── pricing.py                                              │    │
│  │  └── _stock_receivers.py                                     │    │
│  └────────────┬────────┬────────┬────────┬────────┬─────────────┘    │
│           Protocol  Protocol  Protocol  Protocol  Protocol           │
├───────────────┴────────┴────────┴────────┴────────┴──────────────────┤
│                                                                      │
│  ┌─────────────────────── CORE APPS ──────────────────────────────┐  │
│  │                    (shopman-core/*)                             │  │
│  │                                                                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │
│  │  │ offering │ │ stocking │ │ crafting │ │ ordering │          │  │
│  │  │ catálogo │ │ estoque  │ │ produção │ │ pedidos  │          │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │  │
│  │                                                                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │
│  │  │customers │ │   auth   │ │ payments │ │  utils   │          │  │
│  │  │ clientes │ │   auth   │ │  pagam.  │ │  comum   │          │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│              CANAIS DE VENDA (shopman-app/channels/)                  │
│                    web · (futuros: pos, api)                         │
└──────────────────────────────────────────────────────────────────────┘
```

## Protocol/Adapter Pattern

Toda comunicacao entre apps usa `typing.Protocol` (PEP 544) com `@runtime_checkable`. Nenhum app importa outro diretamente.

### Como funciona

1. O app **consumidor** define o Protocol (contrato) no seu codigo
2. O app **provedor** implementa um Adapter
3. A ligacao e feita via settings (dotted path) ou registry (`AppConfig.ready()`)

### Exemplo: Stock

```python
# shopman-app/channels/protocols.py — consumidor define o contrato
@runtime_checkable
class StockBackend(Protocol):
    def check_availability(self, sku: str, quantity: Decimal, ...) -> AvailabilityResult: ...
    def create_hold(self, sku: str, quantity: Decimal, ...) -> HoldResult: ...
    def release_hold(self, hold_id: str) -> None: ...
    def fulfill_hold(self, hold_id: str) -> None: ...

# shopman-app/channels/backends/stock.py — adapter que conecta ao stocking
class StockingBackend:
    def check_availability(self, sku, quantity, ...):
        # Delega para shopman.stocking.service
        ...

# settings.py — ligação via config
SHOPMAN_STOCK_BACKEND = "channels.backends.stock.StockingBackend"
```

### Protocols existentes

| Protocol | Definido em | Adapters |
|----------|-------------|----------|
| `StockBackend` | `channels.protocols` | `StockingBackend`, `NoopStockBackend` |
| `PaymentBackend` | `shopman.payments.protocols` | `MockPaymentBackend`, `EfiPixBackend`, `StripeBackend` |
| `FiscalBackend` | `shopman.ordering.protocols` | `MockFiscalBackend`, `FocusBackend` |
| `AccountingBackend` | `shopman.ordering.protocols` | `MockAccountingBackend`, `ContaazulBackend` |
| `NotificationBackend` | `channels.protocols` | `ConsoleBackend`, `ManychatBackend`, `EmailBackend`, `SmsBackend`, `WebhookBackend`, `WhatsappBackend` |
| `CustomerBackend` | `channels.protocols` | `CustomersBackend`, `NoopCustomerBackend` |
| `PricingBackend` | `channels.protocols` | `CatalogPricingBackend` |

### Vantagens

- **Deploy independente:** cada app pode ser instalado e testado isoladamente
- **Substituibilidade:** trocar o sistema de estoque requer apenas um novo adapter
- **Testabilidade:** mocks implementam o mesmo Protocol, sem dependencias externas
- **Sem dependencias circulares:** cada app depende apenas de `utils`

## Mapa de Dependências

```
utils ← offering
utils ← stocking
utils ← crafting   ← (protocols: stocking, offering)
utils ← ordering
utils ← customers  ← (protocols: ordering)
utils ← auth       ← (protocols: customers)
utils ← payments
```

Setas indicam dependência de pacote. Dependências via Protocol (runtime) são indicadas entre parênteses — não criam acoplamento de pacote.

## Orquestrador — Fluxo de um Pedido

```
1. Session criada (modify_session)
   │
2. Modifiers rodam (ItemPricingModifier, SessionTotalModifier, promoções)
   │
3. Validators de draft rodam
   │
4. Commit (commit_session)
   │
   ├── Validators de commit rodam (StockCheckValidator, etc.)
   ├── Order criada com snapshot dos itens
   ├── order_changed signal (event_type="created")
   │     └── on_order_lifecycle() lê ChannelConfig.pipeline
   │
   ├── Directives enfileiradas conforme pipeline do canal:
   │     ├── customer.ensure   → CustomerEnsureHandler
   │     ├── stock.hold        → StockHoldHandler → StockBackend.create_hold()
   │     ├── notification.send → NotificationSendHandler → NotificationBackend.send()
   │     └── ...
   │
5. Confirmação (conforme modo do canal):
   │  ├── immediate → auto-confirma
   │  ├── optimistic → confirmation.timeout directive
   │  └── manual → aguarda operador
   │
6. Pós-confirmação (se PIX):
   │  └── pix.generate → PixGenerateHandler → PaymentBackend.create_intent()
   │       └── pix.timeout directive agendada
   │
7. Pagamento confirmado (webhook):
      └── stock.commit, notification.send, fulfillment.create
```

## Presets de Canal

Cada canal de venda tem um preset (`channels/presets.py`) que configura o comportamento do pipeline via `ChannelConfig`:

| Preset | Confirmação | Pagamento | Stock Hold TTL | Pipeline on_commit | Pipeline on_confirmed |
|--------|-------------|-----------|----------------|--------------------|-----------------------|
| `pos()` | immediate | `counter` | 5 min | customer.ensure | stock.commit, notification |
| `remote()` | optimistic (10 min) | `pix` (15 min) | 30 min | customer.ensure, stock.hold | pix.generate, notification |
| `marketplace()` | immediate | `external` (pré-pago) | — | customer.ensure | stock.commit |

A configuração cascateia: `Channel.config` → `Shop.defaults` → `ChannelConfig.defaults()`.

Veja [guia de pagamentos](guides/payments.md) para o fluxo PIX completo.

## Mapa de Nomes (suite antiga → repo novo)

Para quem conhece a suite antiga (`django-shopman-suite`):

| Suite Antiga | Repo Novo | App Label |
|-------------|-----------|-----------|
| commons | shopman.utils | utils |
| offerman | shopman.offering | offering |
| stockman | shopman.stocking | stocking |
| craftsman | shopman.crafting | crafting |
| omniman | shopman.ordering | ordering |
| guestman | shopman.customers | customers |
| doorman | shopman.auth | auth |
| *(novo)* | shopman.payments | payments |
