# SPLIT-PLAN — shopman.shop → shop + storefront + backstage

> Dividir o monolito shopman/shop em 3 apps Django com responsabilidades claras.

## Resultado Final

| App | Label | Responsabilidade | Tem views? | Tem models? |
|-----|-------|-----------------|-----------|-------------|
| `shopman.shop` | `shop` | Orquestração: lifecycle, services, adapters, handlers, rules, config, notifications | Não | Sim (shared) |
| `shopman.storefront` | `storefront` | Superfície customer: views, projections, cart, templates, context processors | Sim | Sim (Promotion, Coupon, DeliveryZone) |
| `shopman.backstage` | `backstage` | Superfícies operador: KDS, POS, Gestor de Pedidos, Fechamento, Produção | Sim | Sim (KDS*, DayClosing, OperatorAlert, CashRegister*) |

## Inventário de Movimentação

### Models

| Model | Destino | Justificativa |
|-------|---------|---------------|
| `Shop` | shop | Configuração global, referenciado por todos |
| `Channel` | shop | Entidade de orquestração (ChannelConfig) |
| `RuleConfig` | shop | Engine de regras, cross-cutting |
| `NotificationTemplate` | shop | Dispatch de notificações |
| `OmotenashiCopy` | shop | Configuração de copy, cross-cutting |
| `Promotion` | storefront | Só usado em checkout/cart do customer |
| `Coupon` | storefront | FK → Promotion, só customer |
| `DeliveryZone` | storefront | Validação de endereço no checkout |
| `KDSInstance` | backstage | Estação operacional |
| `KDSTicket` | backstage | Ticket de produção/expedição |
| `DayClosing` | backstage | Fechamento diário |
| `OperatorAlert` | backstage | Alertas para operador |
| `CashRegisterSession` | backstage | POS caixa |
| `CashMovement` | backstage | Sangria, abertura, fechamento |

### Views (67 exports atuais)

**→ storefront (44 views):**
- account.py (13): AccountView, AddressCreate/Update/Delete/SetDefault/LabelUpdate, DataExport, FoodPreferenceToggle, NotificationPrefsToggle, ProfileDisplay/Edit/Update
- auth.py (6): AccessLinkLogin, CustomerLookup, DeviceCheckLogin, Login, RequestCode, VerifyCode
- bridge.py (1): BridgeTokenView
- cart.py (9): AddToCart, ApplyCoupon, CartDrawerContentProj, CartPageContent, CartSetQtyBySku, CartSummary, CartView, QuickAdd, RemoveCoupon
- catalog.py (3): MenuView, ProductDetail, TipsView
- checkout.py (5): CepLookup, CheckoutOrderSummary, Checkout, OrderConfirmation, SimulateIFood
- devices.py (3): DeviceList, DeviceRevoke, DeviceRevokeAll
- home.py (1): HomeView
- info.py (3): HowItWorks, OrderHistory, Sitemap
- payment.py (3): MockPaymentConfirm, PaymentStatus, Payment
- pwa.py (1): OfflineView (+ ManifestView, ServiceWorkerView via urls)
- sse_state.py (1): SkuStateView
- tracking.py (4): OrderCancel, OrderStatusPartial, OrderTracking, Reorder
- welcome.py (1): WelcomeView

**→ backstage (18 views):**
- kds.py (6): KDSDisplay, KDSExpeditionAction, KDSIndex, KDSTicketCheckItem, KDSTicketDone, KDSTicketListPartial
- orders.py (8): OperatorOrders, OrderAdvance, OrderConfirm, OrderDetailPartial, OrderListPartial, OrderMarkPaid, OrderNotes, OrderReject
- pos.py (8): pos_view, pos_cancel_last, pos_cash_close, pos_cash_open, pos_cash_sangria, pos_close, pos_customer_lookup, pos_shift_summary
- production.py (1): bulk_create_work_orders
- closing.py (1): DayClosingView (não exportado do __init__ atual)

### Projections

**→ storefront:**
- cart.py, catalog.py, checkout.py, order_history.py, order_tracking.py, payment.py, product_detail.py, account.py

**→ backstage:**
- kds.py, order_queue.py, pos.py, closing.py, production.py, dashboard.py

**→ shop (shared types):**
- types.py (Availability, OrderItemProjection, FulfillmentProjection, etc.)

### Services (24 modules)

**Ficam em shop (orquestração, usados por handlers ou ambas as superfícies):**
- availability.py, cancellation.py, customer.py, fiscal.py, fulfillment.py, geocoding.py, kds.py, loyalty.py, notification.py, nutrition_from_recipe.py, order_helpers.py, payment.py, pix_confirmation.py, pricing.py, production.py, stock.py, substitutes.py

**→ storefront:**
- checkout.py, checkout_defaults.py, storefront_context.py, ifood_ingest.py, ifood_simulation.py, pickup_slots.py

### Templates

**→ storefront:** `web/templates/storefront/` (57 arquivos)
**→ backstage:** `templates/kds/`, `templates/pedidos/`, `templates/pos/`, `templates/gestao/` (19 arquivos)
**→ shop (shared):** `templates/components/` (18 arquivos) — ficam acessíveis via TEMPLATES dirs

### Static

**→ storefront:** `static/storefront/css/output-v2.css`, `static/storefront/js/`, `static/storefront/v2/`, `static/img/`, `static/icon-*`, `static/js/gestures.js`
**→ backstage:** `static/storefront/css/output-gestao.css` (renomear para `static/backstage/css/`)

### Admin

**Ficam em shop:** Shop, Channel, RuleConfig, NotificationTemplate, OmotenashiCopy admin
**→ storefront:** Promotion, Coupon, DeliveryZone admin
**→ backstage:** KDSInstance, KDSTicket, DayClosing, OperatorAlert, CashRegister admin

### Middleware

| Middleware | Destino | Motivo |
|-----------|---------|--------|
| `ChannelParamMiddleware` | storefront | Só captura ?channel em URLs de customer |
| `OnboardingMiddleware` | backstage | Guarda /gestao/ para staff |
| `APIVersionHeaderMiddleware` | shop | API é do orquestrador |
| `WelcomeGateMiddleware` | storefront | Redirect de customer sem nome |

### Context Processors

**→ storefront (todos):**
- `shop()` — injeta storefront config, customer data, keys
- `omotenashi()` — UX context para customer
- `cart_count()` — badge do carrinho

### Outros

| Arquivo | Destino | Motivo |
|---------|---------|--------|
| `web/cart.py` (CartService) | storefront | Gerencia sessões de compra |
| `web/constants.py` | storefront | STOREFRONT_CHANNEL_REF |
| `webhooks/` (efi, stripe, ifood) | shop | Inbound de terceiros → lifecycle |
| `omotenashi.py` | storefront | UX context builder |
| `management/commands/seed.py` | shop | Seeds globais |
| `management/commands/cleanup_*` | shop | Manutenção |
| `management/commands/suggest_production.py` | shop | Produção = orquestração |

---

## Plano de Execução

### WP-S0: Scaffold apps (sem mover código)

1. Criar `shopman/storefront/` com: `__init__.py`, `apps.py` (StorefrontConfig, label="storefront")
2. Criar `shopman/backstage/` com: `__init__.py`, `apps.py` (BackstageConfig, label="backstage")
3. Adicionar ambos ao `INSTALLED_APPS` (após "shopman.shop")
4. Rodar `make test` — nada quebra (apps vazios)

### WP-S1: Mover models + reset migrations

1. Mover model files:
   - `shop/models/rules.py` (Promotion, Coupon) → `storefront/models/promotions.py`
   - `shop/models/delivery.py` → `storefront/models/delivery.py`
   - `shop/models/kds.py` → `backstage/models/kds.py`
   - `shop/models/closing.py` → `backstage/models/closing.py`
   - `shop/models/alerts.py` → `backstage/models/alerts.py`
   - `shop/models/cash_register.py` → `backstage/models/cash_register.py`
2. Criar `__init__.py` em cada models/ com exports
3. Atualizar `shop/models/__init__.py` — remover exports movidos
4. **Resetar todas as migrações** dos 3 apps (squash para 0001_initial cada)
5. Atualizar ForeignKey strings: `"shop.KDSInstance"` → `"backstage.KDSInstance"`, etc.
6. Atualizar todos os imports no codebase (`from shopman.shop.models import KDSInstance` → `from shopman.backstage.models import KDSInstance`)
7. `make test` — green

### WP-S2: Mover projections

1. Criar `storefront/projections/` — mover: cart, catalog, checkout, order_history, order_tracking, payment, product_detail, account
2. Criar `backstage/projections/` — mover: kds, order_queue, pos, closing, production, dashboard
3. `shop/projections/` mantém APENAS `types.py` (re-exportado nos __init__ de cada app que precisa)
4. Atualizar imports em views e tests
5. `make test` — green

### WP-S3: Mover views + URLs + templates

1. Criar `storefront/views/` — mover 13 módulos de views de customer
2. Criar `storefront/urls.py` com todas as URLs de customer
3. Criar `backstage/views/` — mover 5 módulos de views de operador
4. Criar `backstage/urls.py` com todas as URLs de operador
5. Mover templates:
   - `shop/web/templates/storefront/` → `storefront/templates/storefront/`
   - `shop/templates/kds/` + `pedidos/` + `pos/` + `gestao/` → `backstage/templates/`
6. `shop/templates/components/` fica (template loader encontra por INSTALLED_APPS order)
7. Remover `shop/web/views/` (agora vazio) e `shop/web/urls.py`
8. Atualizar `config/urls.py`:
   ```python
   path("", include("shopman.storefront.urls")),
   path("", include("shopman.backstage.urls")),
   path("api/", include("shopman.shop.api.urls")),
   path("webhooks/", include("shopman.shop.webhooks.urls")),
   ```
9. `make test` — green

### WP-S4: Mover supporting files

1. `web/cart.py` + `web/constants.py` → `storefront/cart.py` + `storefront/constants.py`
2. `omotenashi.py` → `storefront/omotenashi.py`
3. `context_processors.py` → `storefront/context_processors.py` (atualizar settings.TEMPLATES)
4. Middleware split:
   - `ChannelParamMiddleware` + `WelcomeGateMiddleware` → `storefront/middleware.py`
   - `OnboardingMiddleware` → `backstage/middleware.py`
   - `APIVersionHeaderMiddleware` fica em `shop/middleware.py`
5. Services de storefront: mover `checkout.py`, `checkout_defaults.py`, `storefront_context.py`, `ifood_ingest.py`, `ifood_simulation.py`, `pickup_slots.py` → `storefront/services/`
6. Static split: renomear/mover CSS gestao para `backstage/static/backstage/`
7. Admin split: mover registrations correspondentes
8. `make test` — green

### WP-S5: Wiring apps.py

1. `shop/apps.py` — mantém: handlers, rules, lifecycle signals, nutrition signal, refs. Remove qualquer referência a storefront/backstage.
2. `storefront/apps.py` — ready() não precisa de signals (views são passivas). Pode registrar checks específicos.
3. `backstage/apps.py` — ready() pode registrar SSE emitters de backstage se houver.
4. `make test` — green

### WP-S6: Redistribuir tests

1. Tests de views/projections de customer → `storefront/tests/`
2. Tests de views/projections de operator → `backstage/tests/`
3. Tests de lifecycle, services, adapters, handlers → ficam em `shop/tests/`
4. Integration tests que cruzam apps ficam em `shop/tests/integration/`
5. `make test` — green, contagem igual (~1.209)

### WP-S7: Cleanup + verificação final

1. Deletar `shop/web/` (diretório agora vazio)
2. Verificar zero imports cruzados ilegais (storefront não importa backstage e vice-versa)
3. Ambos podem importar de shop (orquestrador)
4. `ruff check` + `make test` — green
5. Atualizar CLAUDE.md com nova estrutura
6. Atualizar memory

---

## Regras de Dependência (pós-split)

```
storefront ──imports──→ shop ←──imports── backstage
     ↓                   ↓                    ↓
  (never)            packages/            (never)
                   ↗  ↑  ↑  ↖
          offerman stockman orderman craftsman ...
```

- `storefront` e `backstage` NUNCA importam um do outro
- Ambos importam de `shop` (services, config, notifications, models shared)
- Ambos importam de `packages/` (orderman, offerman, etc.)
- `shop` NUNCA importa de `storefront` ou `backstage`

---

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| RuleConfig model fica em shop mas Promotion/Coupon em storefront — rules engine precisa de FK? | Não: RuleConfig referencia por JSONField (tipo/ref), não FK. Zero acoplamento. |
| `templates/components/` shared — quem mantém? | Fica em shop. Django template loader encontra por INSTALLED_APPS order. |
| `SkuStateView` usado por storefront E POS (SSE badge) | Fica em storefront (POS consome via fetch/SSE do mesmo endpoint — não precisa estar no backstage) |
| Circular: storefront context_processor importa CartService que importa services de shop | Unidirecional: storefront → shop. CartService importa shop.services (allowed). |

---

## Estimativa

| WP | Complexidade | Arquivos tocados |
|----|-------------|-----------------|
| WP-S0 | Trivial | 4 novos + settings |
| WP-S1 | Média | ~30 (models + migrations + imports) |
| WP-S2 | Média | ~40 (projections + imports em views/tests) |
| WP-S3 | Alta | ~60 (views, urls, templates, imports) |
| WP-S4 | Média | ~25 (supporting files) |
| WP-S5 | Baixa | 3 (apps.py files) |
| WP-S6 | Média | ~50 (test files moved + imports) |
| WP-S7 | Baixa | 5 (cleanup + docs) |

**Total: ~7 WPs substantivos, executáveis sequencialmente.**
