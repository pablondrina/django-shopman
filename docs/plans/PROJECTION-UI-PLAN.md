# Plano de Projections + UI — Django Shopman

Data: 2026-04-13
Base: Constituição Semântica, Matriz Executiva, Penguin UI (Tailwind + Alpine.js) + HTMX

## 1. Tese

Hoje os templates consomem dados diretamente dos domain models, services e helpers.
Cada view monta seu context dict ad-hoc, misturando queries, enrichments e formatação.
Isso funciona, mas viola dois princípios constitucionais:

- **2.2** — a suite deve falar em compromissos, não em tabelas
- **3.4** — core não depende de framework para existir

A solução: **Projections** — read models tipados que traduzem o estado do domínio
para o que a UI (ou API) precisa consumir. A view vira um thin controller que pede
uma projection e a entrega ao template. O template consome uma interface estável,
não os internals do domínio.

Ao mesmo tempo, migramos o design system para **Penguin UI** (Tailwind v4 + Alpine.js),
mantendo a regra de ouro:

> **Alpine.js → DOM** (estado local, toggles, modals, validação client-side)
> **HTMX → Server** (GET, POST, polling, swaps, loading states)

## 2. Arquitetura de Projections

```
Domain Models  →  Projection Builder  →  Projection (dataclass/TypedDict)  →  View  →  Template
     │                    │                        │
  orderman.Order    services + helpers      CartProjection
  offerman.Product  availability checks    CatalogItemProjection
  stockman.Hold     pricing + promos       OrderTrackingProjection
  craftsman.WO      enrichments            ProductionBoardProjection
  guestman.Customer                        CustomerProfileProjection
  payman.Intent                            CheckoutProjection
```

Cada projection é um **dataclass** ou **TypedDict** em `shopman/shop/projections/`.
Os builders ficam no mesmo módulo. Views chamam o builder, passam o resultado ao template.

### Regras

- Projections são read-only e imutáveis
- Nunca expõem PKs, querysets ou model instances ao template
- Valores monetários já vêm formatados (`price_display: str`) além do raw (`price_q: int`)
- Disponibilidade é um enum/string canônico, não um bool
- Projections são a interface de contrato com templates E com a futura API REST

## 3. Inventário de Telas e Projections Necessárias

### 3.1. Storefront — Cliente

| Tela | URL | Template Atual | Projection |
|------|-----|----------------|------------|
| Home / Menu | `/menu/` | `storefront/menu.html` | `CatalogProjection` |
| Produto (PDP) | `/produto/<slug>/` | `storefront/product_detail.html` | `ProductDetailProjection` |
| Carrinho | `/carrinho/` | `storefront/cart.html` | `CartProjection` |
| Checkout | `/checkout/` | `storefront/checkout.html` | `CheckoutProjection` |
| Pagamento PIX | `/pagamento/<ref>/` | `storefront/payment.html` | `PaymentProjection` |
| Tracking | `/pedido/<ref>/` | `storefront/tracking.html` | `OrderTrackingProjection` |
| Confirmação | `/confirmacao/<ref>/` | `storefront/order_confirmation.html` | `OrderConfirmationProjection` |
| Conta | `/conta/` | `storefront/account.html` | `CustomerProfileProjection` |
| Pedidos | `/conta/pedidos/` | `storefront/orders.html` | `OrderHistoryProjection` |
| Endereços | `/conta/enderecos/` | `storefront/addresses.html` | `AddressListProjection` |
| Loyalty | `/conta/fidelidade/` | `storefront/loyalty.html` | `LoyaltyProjection` |
| Login | `/entrar/` | `storefront/login.html` | (mínimo, sem projection complexa) |

### 3.2. Operador

| Tela | URL | Template Atual | Projection |
|------|-----|----------------|------------|
| Fila de Pedidos | `/gestor/pedidos/` | `pedidos/index.html` | `OrderQueueProjection` |
| Detalhe Pedido | `/gestor/pedidos/<ref>/detail/` | `pedidos/partials/detail.html` | `OperatorOrderProjection` |
| KDS Picking | `/gestor/kds/` | `kds/display.html` | `KDSBoardProjection` |
| KDS Expedição | `/gestor/kds/` | `kds/display.html` | `KDSExpeditionProjection` |
| POS | `/gestor/pos/` | `pos/index.html` | `POSProjection` |
| Produção | `/gestor/producao/` | `gestor/producao/index.html` | `ProductionBoardProjection` |
| Fechamento | `/gestor/fechamento/` | `gestor/fechamento/index.html` | `DayClosingProjection` |

### 3.3. Admin / Dashboard

| Tela | URL | Projection |
|------|-----|------------|
| Dashboard | `/admin/shop/dashboard/` | `DashboardProjection` |

## 4. Detalhamento das Projections

### 4.1. CatalogProjection

Alimenta: Home, Menu, busca, listagens por categoria/coleção.

```python
@dataclass(frozen=True)
class CatalogItemProjection:
    sku: str
    slug: str
    name: str
    short_description: str
    image_url: str | None
    category: str | None
    tags: list[str]

    # Preço
    base_price_q: int
    price_display: str            # "R$ 12,90"
    has_promotion: bool
    original_price_display: str | None  # "R$ 15,90" (riscado)
    promotion_label: str | None   # "20% OFF"

    # Disponibilidade (canônica, não bool)
    availability: str             # "available", "low_stock", "planned_ok", "unavailable"
    availability_label: str       # "Disponível", "Últimas unidades", etc.
    can_add_to_cart: bool

    # Dietary / atributos
    dietary_info: list[str]
    is_new: bool
    is_featured: bool

@dataclass(frozen=True)
class CatalogProjection:
    items: list[CatalogItemProjection]
    categories: list[CategoryProjection]
    featured: list[CatalogItemProjection]
    happy_hour: HappyHourProjection | None
    shop_status: ShopStatusProjection
```

### 4.2. ProductDetailProjection

Alimenta: PDP.

```python
@dataclass(frozen=True)
class ProductDetailProjection:
    sku: str
    slug: str
    name: str
    long_description: str
    image_url: str | None
    gallery: list[str]

    # Preço
    base_price_q: int
    price_display: str
    has_promotion: bool
    original_price_display: str | None
    promotion_label: str | None

    # Disponibilidade
    availability: str
    availability_label: str
    can_add_to_cart: bool
    available_qty: int | None     # para controle de qty no frontend
    max_qty: int

    # Composição (bundles)
    components: list[ComponentProjection] | None
    is_bundle: bool

    # Dietary / atributos
    dietary_info: list[str]
    serves: str | None
    allergens: list[str]

    # Alternativas (quando indisponível)
    alternatives: list[CatalogItemProjection]

    # Upsell / cross-sell
    suggestions: list[CatalogItemProjection]
```

### 4.3. CartProjection

Alimenta: Carrinho (drawer e página), mini-cart count.

```python
@dataclass(frozen=True)
class CartItemProjection:
    sku: str
    name: str
    qty: int
    unit_price_q: int
    total_price_q: int
    price_display: str
    image_url: str | None

    # Disponibilidade no momento
    is_sellable: bool
    available_qty: int | None
    availability_warning: str | None  # "Estoque insuficiente", etc.

    # Descontos aplicados
    discounts: list[DiscountLineProjection]

@dataclass(frozen=True)
class CartProjection:
    items: list[CartItemProjection]
    items_count: int
    subtotal_q: int
    subtotal_display: str
    discount_total_q: int
    discount_display: str | None
    delivery_fee_q: int | None
    delivery_fee_display: str | None
    total_q: int
    total_display: str

    # Coupon
    coupon_code: str | None
    coupon_label: str | None

    # Warnings globais
    warnings: list[str]
    has_unavailable_items: bool

    # Loyalty
    points_to_earn: int | None
    redeem_applied_q: int | None
```

### 4.4. CheckoutProjection

Alimenta: Checkout.

```python
@dataclass(frozen=True)
class CheckoutProjection:
    cart: CartProjection
    fulfillment_options: list[FulfillmentOptionProjection]  # pickup, delivery
    selected_fulfillment: str

    # Pagamento
    payment_methods: list[PaymentMethodProjection]  # pix, card, cash
    selected_payment: str | None

    # Endereço (delivery)
    addresses: list[AddressProjection]
    selected_address_id: int | None
    delivery_fee_q: int | None

    # Horário
    time_slots: list[TimeSlotProjection] | None
    selected_slot: str | None
    is_preorder: bool

    # Cliente
    customer_name: str | None
    customer_phone: str | None

    # Loyalty
    loyalty_balance: int | None
    max_redeemable_q: int | None
    redeem_applied_q: int | None

    # Cupom
    coupon_code: str | None
    coupon_discount_q: int | None

    # Validações
    can_submit: bool
    validation_errors: list[str]
```

### 4.5. OrderTrackingProjection

Alimenta: Tracking, confirmação.

```python
@dataclass(frozen=True)
class TimelineStepProjection:
    status: str
    label: str
    timestamp: str | None
    is_current: bool
    is_completed: bool

@dataclass(frozen=True)
class OrderTrackingProjection:
    ref: str
    status: str
    status_label: str
    placed_at: str
    total_q: int
    total_display: str

    # Timeline
    timeline: list[TimelineStepProjection]
    current_step: str

    # Items
    items: list[OrderItemProjection]

    # Pagamento
    payment_method: str
    payment_status: str
    pix_payload: str | None       # para QR code
    pix_expires_at: str | None

    # Fulfillment
    fulfillment_type: str         # "pickup", "delivery"
    estimated_time: str | None
    delivery_address: str | None
    tracking_url: str | None

    # Ações disponíveis
    can_cancel: bool
    cancel_deadline: str | None
```

### 4.6. ProductionBoardProjection

Alimenta: Tela de produção (operador).

```python
@dataclass(frozen=True)
class WorkOrderCardProjection:
    ref: str
    recipe_name: str
    status: str                   # "planned", "started", "finished", "void"
    status_label: str
    planned_qty: str
    started_qty: str | None
    finished_qty: str | None
    yield_rate: str | None        # "92%"
    loss: str | None
    operator_ref: str | None
    position_ref: str | None
    target_date: str
    started_at: str | None
    urgency: str                  # "normal", "soon", "overdue"

@dataclass(frozen=True)
class ProductionBoardProjection:
    date: str
    work_orders: list[WorkOrderCardProjection]
    counts: ProductionCountsProjection  # by status
    suggestions: list[ProductionSuggestionProjection]
```

### 4.7. KDSBoardProjection

Alimenta: KDS picking e expedição.

```python
@dataclass(frozen=True)
class KDSTicketProjection:
    order_ref: str
    ticket_id: int
    items: list[KDSItemProjection]
    elapsed_minutes: int
    urgency: str                  # "green", "yellow", "red"
    status: str
    fulfillment_type: str
    customer_name: str | None
    notes: str | None

@dataclass(frozen=True)
class KDSBoardProjection:
    instance_name: str
    tickets: list[KDSTicketProjection]
    counts: KDSCountsProjection
```

### 4.8. CustomerProfileProjection

Alimenta: Conta, perfil, loyalty.

```python
@dataclass(frozen=True)
class CustomerProfileProjection:
    ref: str
    name: str
    phone: str | None
    email: str | None
    member_since: str

    # Loyalty
    loyalty_tier: str | None
    loyalty_points: int
    tier_label: str | None
    next_tier: str | None
    points_to_next_tier: int | None
    stamps: list[StampCardProjection] | None

    # Histórico
    total_orders: int
    total_spent_display: str
    last_order_date: str | None

    # Endereços
    addresses: list[AddressProjection]

    # Preferências
    favorite_items: list[str]
    dietary_preferences: list[str]
```

### 4.9. OrderQueueProjection e OperatorOrderProjection

Alimenta: Fila de pedidos (operador) e detalhe.

```python
@dataclass(frozen=True)
class OrderCardProjection:
    ref: str
    status: str
    status_label: str
    customer_name: str | None
    channel: str
    fulfillment_type: str
    items_summary: str            # "3 itens"
    total_display: str
    placed_at: str
    elapsed_minutes: int
    urgency: str
    payment_status: str
    has_notes: bool

@dataclass(frozen=True)
class OrderQueueProjection:
    orders: list[OrderCardProjection]
    counts_by_status: dict[str, int]
    active_filter: str | None
```

## 5. Design System — Penguin UI

### 5.1. Setup

Penguin UI é copy-paste (sem npm package). Componentes são blocos de HTML + Tailwind + Alpine.

Dependências:
- **Tailwind CSS v4+** (via CDN ou build)
- **Alpine.js v3+** (via CDN)
- **HTMX** (via CDN)

### 5.2. Componentes Penguin UI por Tela

| Tela | Componentes Penguin UI |
|------|----------------------|
| Menu/Catálogo | Card, Badge, Skeleton (loading), Tabs (categorias), Banner (happy hour) |
| PDP | Card, Badge, Button, Alert (indisponível), Accordion (detalhes), Carousel (galeria) |
| Carrinho | Card, Button, Alert (warnings), Badge (qty), Modal (alternativas) |
| Checkout | Radio (fulfillment/payment), Select (endereço), Text-input, Button, Steps (progresso), Alert |
| Pagamento | Card (QR code), Badge (status), Spinner (polling), Alert (expirado) |
| Tracking | Steps (timeline), Card, Badge (status), Button (cancelar) |
| Conta | Tabs (seções), Card, Table (pedidos), Badge (tier) |
| Login | Text-input (phone), Button, Alert |
| Fila Pedidos | Table, Badge (status), Dropdown (filtros), Card |
| KDS | Card (tickets), Badge (urgência), Button (ações), Toast (atualização) |
| POS | Card, Button, Text-input, Modal, Badge |
| Produção | Card, Badge (status), Button, Text-input (qty), Table (sugestões) |
| Fechamento | Table, Text-input (qty), Badge (classificação), Button |
| Dashboard | Card (KPI), Table, Badge |

### 5.3. Regra de Ouro: Alpine ↔ HTMX

```
┌─────────────────────────────────────────────────┐
│                  HTMX (Server)                   │
│  hx-get, hx-post, hx-trigger, hx-swap           │
│  hx-target, hx-indicator, hx-push-url            │
│  hx-on::before-request / after-request           │
│                                                   │
│  Tudo que envolve comunicação com o servidor      │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│                Alpine.js (DOM)                    │
│  x-data, x-show, x-bind, x-on, x-text           │
│  x-transition, x-ref, $store, $dispatch           │
│  @click, @keydown, @input                         │
│                                                   │
│  Tudo que é estado local na tela                  │
└─────────────────────────────────────────────────┘

NUNCA: onclick="...", document.getElementById, classList.toggle
EXCEÇÃO: APIs do browser sem equivalente Alpine (IntersectionObserver, geolocation, clipboard)
```

### 5.4. Padrão de Template com Penguin UI + HTMX + Projections

```html
{# Exemplo: Card de produto consumindo CatalogItemProjection #}

<div class="relative overflow-hidden rounded-xl border border-neutral-300 bg-white"
     x-data="{ imgLoaded: false }">

  {# Imagem com skeleton loading (Alpine) #}
  <div class="aspect-square bg-neutral-100" x-show="!imgLoaded">
    {# Penguin: Skeleton #}
    <div class="h-full w-full animate-pulse bg-neutral-200"></div>
  </div>
  <img src="{{ item.image_url }}"
       alt="{{ item.name }}"
       class="aspect-square w-full object-cover"
       @load="imgLoaded = true"
       x-show="imgLoaded" x-transition>

  {# Badges (Penguin) #}
  <div class="absolute top-2 left-2 flex gap-1">
    {% if item.has_promotion %}
      <span class="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
        {{ item.promotion_label }}
      </span>
    {% endif %}
    {% if item.availability == "low_stock" %}
      <span class="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
        {{ item.availability_label }}
      </span>
    {% endif %}
  </div>

  <div class="p-4">
    <h3 class="text-sm font-semibold text-neutral-900">{{ item.name }}</h3>
    <p class="mt-1 text-lg font-bold text-neutral-900">{{ item.price_display }}</p>
    {% if item.original_price_display %}
      <p class="text-sm text-neutral-500 line-through">{{ item.original_price_display }}</p>
    {% endif %}

    {# Botão — HTMX para server, Alpine para feedback visual #}
    {% if item.can_add_to_cart %}
      <button class="mt-3 w-full rounded-lg bg-black px-4 py-2 text-sm font-medium text-white
                     hover:bg-neutral-800 disabled:opacity-50"
              hx-post="/carrinho/adicionar/"
              hx-vals='{"sku": "{{ item.sku }}", "qty": 1}'
              hx-target="#cart-count"
              hx-swap="innerHTML"
              hx-indicator="#loading-{{ item.sku }}"
              x-data="{ added: false }"
              hx-on::after-request="added = true; setTimeout(() => added = false, 2000)">
        <span x-show="!added">Adicionar</span>
        <span x-show="added" x-transition>Adicionado ✓</span>
      </button>
    {% else %}
      <button class="mt-3 w-full rounded-lg bg-neutral-200 px-4 py-2 text-sm font-medium text-neutral-500"
              disabled>
        {{ item.availability_label }}
      </button>
    {% endif %}
  </div>
</div>
```

## 6. Estrutura de Arquivos

```
shopman/shop/projections/
├── __init__.py
├── types.py                    # Shared types: DiscountLineProjection, AddressProjection, etc.
├── catalog.py                  # CatalogProjection, CatalogItemProjection, build_catalog()
├── product_detail.py           # ProductDetailProjection, build_product_detail()
├── cart.py                     # CartProjection, CartItemProjection, build_cart()
├── checkout.py                 # CheckoutProjection, build_checkout()
├── tracking.py                 # OrderTrackingProjection, build_tracking()
├── customer.py                 # CustomerProfileProjection, build_customer_profile()
├── order_queue.py              # OrderQueueProjection, build_order_queue()
├── production.py               # ProductionBoardProjection, build_production_board()
├── kds.py                      # KDSBoardProjection, build_kds_board()
├── pos.py                      # POSProjection, build_pos()
├── dashboard.py                # DashboardProjection, build_dashboard()
└── closing.py                  # DayClosingProjection, build_day_closing()

shopman/shop/web/
├── templates/
│   ├── base.html               # Penguin UI base: Tailwind v4 + Alpine + HTMX CDN
│   ├── components/             # Penguin UI partials reutilizáveis
│   │   ├── product_card.html
│   │   ├── badge.html
│   │   ├── price.html
│   │   ├── availability.html
│   │   ├── timeline.html
│   │   ├── order_card.html
│   │   └── ...
│   ├── storefront/             # Templates de cliente (consomem projections)
│   └── operator/               # Templates de operador (consomem projections)
```

## 7. Fases de Execução

### Fase 1 — Fundação (infra + primeiras projections)

**Objetivo:** Criar a infra de projections e migrar as 3 telas mais acessadas.

1. Criar `shopman/shop/projections/` com types base
2. Implementar `CatalogProjection` + builder (extrai lógica de `_annotate_products`)
3. Implementar `CartProjection` + builder (extrai lógica de `CartService.get_cart`)
4. Implementar `ProductDetailProjection` + builder
5. Setup Penguin UI no `base.html` (Tailwind v4 CDN + Alpine + HTMX)
6. Migrar `menu.html` para consumir `CatalogProjection` + Penguin UI
7. Migrar `cart.html` idem
8. Migrar `product_detail.html` idem
9. Testes: verificar que projections são construídas corretamente

**Entrega:** As 3 telas core do storefront funcionam com projections + novo design system.

### Fase 2 — Checkout + Pagamento + Tracking

**Objetivo:** Fechar o loop de compra.

1. `CheckoutProjection` + builder
2. `PaymentProjection` + builder
3. `OrderTrackingProjection` + builder
4. `OrderConfirmationProjection` + builder
5. Migrar templates correspondentes para Penguin UI
6. Testes do fluxo completo: menu → cart → checkout → payment → tracking

**Entrega:** Fluxo de compra inteiro com projections + Penguin UI.

### Fase 3 — Conta + Histórico

**Objetivo:** Área do cliente.

1. `CustomerProfileProjection` + builder
2. `OrderHistoryProjection` + builder
3. `LoyaltyProjection` + builder
4. `AddressListProjection` + builder
5. Migrar templates da área de conta
6. Testes

**Entrega:** Área do cliente completa com projections.

### Fase 4 — Operador (Pedidos + KDS + Produção)

**Objetivo:** Telas do operador.

1. `OrderQueueProjection` + builder
2. `OperatorOrderProjection` + builder
3. `KDSBoardProjection` + builder
4. `ProductionBoardProjection` + builder
5. `DayClosingProjection` + builder
6. Migrar templates de operador para Penguin UI
7. Testes

**Entrega:** Painel do operador com projections.

### Fase 5 — POS + Dashboard + API

**Objetivo:** Fechar e preparar API.

1. `POSProjection` + builder
2. `DashboardProjection` + builder
3. Migrar POS e dashboard para Penguin UI
4. Definir se API REST consome as mesmas projections (provavelmente sim, com serializers)
5. Testes end-to-end

**Entrega:** Todas as telas com projections + design system unificado. API pronta para usar as mesmas projections.

## 8. Decisões Arquiteturais

### Projection ≠ Serializer

Projections são a camada de leitura do domínio. Serializers DRF são a camada de serialização HTTP. A API pode usar projections como fonte:

```python
# views/api/catalog.py
class CatalogAPIView(APIView):
    def get(self, request):
        projection = build_catalog(channel_ref="web", ...)
        return Response(CatalogSerializer(projection).data)
```

### Disponibilidade como enum, não bool

```python
class Availability(str, Enum):
    AVAILABLE = "available"
    LOW_STOCK = "low_stock"
    PLANNED_OK = "planned_ok"     # não tem físico, mas produção planejada cobre
    DEMAND_OK = "demand_ok"       # aceita demanda sem estoque
    UNAVAILABLE = "unavailable"
```

Isso alinha com a constituição (seção 4.2 — Stockman): disponibilidade canônica
distingue available, planned, expected, unavailable.

### Preços sempre dual

Toda projection de preço carrega o raw (`_q` em centavos) e o display (string formatada).
Templates usam o display. Lógica Alpine usa o raw.

### Projections são o contrato

Se a UI precisa de um dado, ele deve existir na projection. Se não existe, adiciona.
O template nunca faz queries, nunca importa models, nunca chama services.

## 9. O que NÃO fazer

- Não criar projections para telas que não existem ainda
- Não inventar features durante a migração
- Não mexer nos domain models — as projections consomem, não alteram
- Não duplicar lógica de negócio nos builders — eles orquestram services existentes
- Não abandonar HTMX em favor de client-side rendering
- Não usar `onclick`, `document.getElementById`, `classList.toggle` — Alpine.js sempre
