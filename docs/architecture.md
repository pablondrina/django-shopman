# Arquitetura — Django Shopman

> ⚠️ **Documento em revisão (2026-04-18)**: este arquivo ainda reflete terminologia anterior em alguns pontos (ex.: `backends/` virou `adapters/` no cleanup-2; os nomes de classes `StockingBackend`, `CustomersBackend` etc. podem estar desatualizados). Para a verdade atual, consulte [docs/reference/system-spec.md](reference/system-spec.md). Correções estruturais deste arquivo em WP separado.

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
   │  ├── immediate    → auto-confirma
   │  ├── auto_confirm → confirmation.timeout directive (auto-confirma no prazo)
   │  ├── auto_cancel  → confirmation.timeout directive (auto-cancela no prazo)
   │  └── manual       → aguarda operador
   │
6. Pós-confirmação (se PIX):
   │  └── pix.generate → PixGenerateHandler → PaymentBackend.create_intent()
   │       └── pix.timeout directive agendada
   │
7. Pagamento confirmado (webhook):
      └── stock.commit, notification.send, fulfillment.create, loyalty.earn
```

## Configuração de Canal (cascata `ChannelConfig`)

Não existe sistema de presets factory em código (o conceito foi planejado em planos arquivados mas nunca implementado; referências remanescentes são resíduo). Cada canal é configurado via dict literal em seed, ou pelo admin em runtime, no campo `Channel.config` (JSONField).

A dataclass `ChannelConfig` em [shopman/shop/config.py](../shopman/shop/config.py) define 8 aspectos com defaults sensatos: `confirmation`, `payment`, `fulfillment`, `stock`, `notifications`, `pricing`, `editing`, `rules`. A config efetiva é resolvida por `ChannelConfig.for_channel(channel)` via `deep_merge(dataclass_defaults, shop.defaults, channel.config)` — dicts merged recursivamente, lists replaced.

Exemplos (de Nelson seed):

| Canal | Confirmação | Pagamento | Stock hold TTL | Editing | Notes |
|-------|-------------|-----------|----------------|---------|-------|
| `balcao` | `immediate` | `counter` | — | `open` | POS screen |
| `delivery` / `web` | `auto_confirm` (5 min) | `[pix, card]` | 30 min | `open` | Storefront |
| `whatsapp` | `auto_confirm` (5 min) | `[pix, card]` | 30 min | `open` | Fluxo via bot |
| `ifood` | `auto_cancel` (5 min) | `external` | — | `locked` | Pré-pago marketplace |

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
