# Arquitetura — Django Shopman

## Visão Geral

Django Shopman é composto por **8 apps core** independentes e um **orquestrador** (`shopman/`) que os conecta para cenários de negócio concretos. Cada app core é um pacote pip instalável separadamente.

## Diagrama de Camadas

```
┌──────────────────────────────────────────────────────────────────────┐
│                         PROJETO DJANGO                               │
│                     (config/)                              │
│                   settings.py · urls.py · wsgi                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              SHOP (shopman/shop/)                       │    │
│  │         Shop (singleton), Promotion, Coupon                  │    │
│  │         Configuração global + defaults de canal              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │            SHOPMAN — Orquestrador (shopman/shop/)        │    │
│  │                                                              │    │
│  │  config.py   presets.py   topics.py   hooks.py   setup.py   │    │
│  │                                                              │    │
│  │  handlers/                    backends/                      │    │
│  │  ├── stock.py                 ├── stock.py                   │    │
│  │  ├── payment.py               ├── payment_mock.py            │    │
│  │  ├── notification.py          ├── payment_efi.py             │    │
│  │  ├── confirmation.py          ├── payment_stripe.py          │    │
│  │  ├── customer.py              ├── notification_*.py (6)      │    │
│  │  ├── fiscal.py                ├── customer.py                │    │
│  │  ├── accounting.py            ├── pricing.py                 │    │
│  │  ├── returns.py               ├── fiscal_*.py                │    │
│  │  ├── fulfillment.py           └── accounting_*.py            │    │
│  │  ├── loyalty.py                                              │    │
│  │  ├── pricing.py                                              │    │
│  │  └── _stock_receivers.py                                     │    │
│  └────────────┬────────┬────────┬────────┬────────┬─────────────┘    │
│           Protocol  Protocol  Protocol  Protocol  Protocol           │
├───────────────┴────────┴────────┴────────┴────────┴──────────────────┤
│                                                                      │
│  ┌─────────────────────── CORE APPS ──────────────────────────────┐  │
│  │                    (packages/*)                                 │  │
│  │                                                                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │
│  │  │offerman  │ │stockman  │ │craftsman │ │orderman  │          │  │
│  │  │ catálogo │ │ estoque  │ │ produção │ │ pedidos  │          │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │  │
│  │                                                                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │
│  │  │guestman  │ │ doorman  │ │  payman  │ │  utils   │          │  │
│  │  │ clientes │ │   auth   │ │  pagam.  │ │  comum   │          │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│              CANAIS DE VENDA (shopman/shop/web/)                 │
│                    web · api · (futuro: pos)                         │
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
# shopman/shop/protocols.py — consumidor define o contrato
@runtime_checkable
class StockBackend(Protocol):
    def check_availability(self, sku: str, quantity: Decimal, ...) -> AvailabilityResult: ...
    def create_hold(self, sku: str, quantity: Decimal, ...) -> HoldResult: ...
    def release_hold(self, hold_id: str) -> None: ...
    def fulfill_hold(self, hold_id: str) -> None: ...

# shopman/shop/backends/stock.py — adapter que conecta ao stockman
class StockingBackend:
    def check_availability(self, sku, quantity, ...):
        # Delega para shopman.stockman.service
        ...

# settings.py — ligação via config
SHOPMAN_STOCK_BACKEND = "channels.backends.stock.StockingBackend"
```

### Protocols existentes

| Protocol | Definido em | Adapters |
|----------|-------------|----------|
| `StockBackend` | `shopman/protocols` | `StockingBackend`, `NoopStockBackend` |
| `PaymentBackend` | `shopman.payman.protocols` | `MockPaymentBackend`, `EfiPixBackend`, `StripeBackend` |
| `FiscalBackend` | `shopman.orderman.protocols` | `MockFiscalBackend`, `FocusBackend` |
| `AccountingBackend` | `shopman.orderman.protocols` | `MockAccountingBackend`, `ContaazulBackend` |
| `NotificationBackend` | `shopman/protocols` | `ConsoleBackend`, `ManychatBackend`, `EmailBackend`, `SmsBackend`, `WebhookBackend`, `WhatsappBackend` |
| `CustomerBackend` | `shopman/protocols` | `CustomersBackend`, `NoopCustomerBackend` |
| `PricingBackend` | `shopman/protocols` | `OffermanBackend`, `CatalogPricingBackend`, `ChannelPricingBackend` |

### Vantagens

- **Deploy independente:** cada app pode ser instalado e testado isoladamente
- **Substituibilidade:** trocar o sistema de estoque requer apenas um novo adapter
- **Testabilidade:** mocks implementam o mesmo Protocol, sem dependencias externas
- **Sem dependencias circulares:** cada app depende apenas de `utils`

## Mapa de Dependências

```
utils ← offerman
utils ← stockman
utils ← craftsman  ← (protocols: stockman, offerman)
utils ← orderman
utils ← guestman   ← (protocols: orderman)
utils ← doorman    ← (protocols: guestman)
utils ← payman
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
   ├── Serviços chamados diretamente pelo lifecycle (síncronos):
   │     ├── customer.ensure   → services/customer.py (chamada direta)
   │     ├── stock.hold        → services/stock.py → adapter.create_hold()
   │     ├── payment.initiate  → services/payment.py → adapter.create_intent()
   │     └── fulfillment.create → services/fulfillment.py
   │
   ├── Directives assíncronas criadas por services:
   │     ├── notification.send → NotificationSendHandler → NotificationBackend.send()
   │     ├── loyalty.earn      → LoyaltyEarnHandler
   │     ├── fiscal.emit_nfce  → NFCeEmitHandler
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
      └── stock.commit, notification.send, fulfillment.create, loyalty.earn
```

## Presets de Canal

Cada canal de venda tem um preset (`shopman/presets.py`) que configura o comportamento do pipeline via `ChannelConfig`:

| Preset | Confirmação | Pagamento | Stock Hold TTL | Pipeline on_commit | Pipeline on_confirmed |
|--------|-------------|-----------|----------------|--------------------|-----------------------|
| `pos()` | immediate | `counter` | 5 min | customer.ensure | stock.commit, notification, loyalty.earn |
| `remote()` | optimistic (10 min) | `pix` (15 min) | 30 min | customer.ensure, stock.hold | pix.generate, notification, loyalty.earn |
| `marketplace()` | immediate | `external` (pré-pago) | — | customer.ensure | stock.commit |

A configuração cascateia: `Channel.config` → `Shop.defaults` → `ChannelConfig.defaults()`.

Veja [guia de pagamentos](guides/payments.md) para o fluxo PIX completo.

## Namespaces dos Core Apps

| Persona | Pacote pip | Namespace Python | App Label |
|---------|-----------|-----------------|-----------|
| Utils | shopman-utils | shopman.utils | utils |
| Offerman | shopman-offerman | shopman.offerman | offerman |
| Stockman | shopman-stockman | shopman.stockman | stockman |
| Craftsman | shopman-craftsman | shopman.craftsman | craftsman |
| Orderman | shopman-orderman | shopman.orderman | orderman |
| Guestman | shopman-guestman | shopman.guestman | guestman |
| Doorman | shopman-doorman | shopman.doorman | doorman |
| Payman | shopman-payman | shopman.payman | payman |
