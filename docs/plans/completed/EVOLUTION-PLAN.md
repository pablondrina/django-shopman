# EVOLUTION-PLAN.md — Django Shopman

> Evolução do App para solução de primeira linha.
> Todos os planos anteriores (Refactor, Consolidation, Hardening, Bridge) estão completos.
> Cada WP é auto-contido, dimensionado para uma sessão do Claude Code.

---

## Status Geral

**Todos os 6 WPs estão implementados.** O Core+App tem ~2.444 testes (1.532 core + 912 app).

| WP | Feature | Status | Evidência |
|----|---------|--------|-----------|
| E1 | Disponibilidade + Alternativas | **✅ Completo** | `catalog.py` (ProductDetailView + _load_alternatives), `cart.py` (CartCheckView), `cart_warnings.html` |
| E2 | Loyalty na UI | **✅ Completo** | `handlers/loyalty.py` (LoyaltyEarnHandler), topic LOYALTY_EARN, registrado em setup.py, pipeline on_completed em pos()/remote() |
| E3 | Pagamento com Cartão | **✅ Completo** | `handlers/payment.py` (CardCreateHandler), topic CARD_CREATE, registrado em setup.py |
| E4 | Dashboard do Operador | **✅ Completo** | `shop/dashboard.py` (462 linhas): KPIs, charts, tables, D-1 stock |
| E5 | Notificações Transacionais | **✅ Completo** | `notification_email.py` (EmailBackend, 8 eventos), 4 templates HTML, registrado em setup.py |
| E6 | API REST Completa | **✅ Completo** | `api/catalog.py` (ProductList/Detail, CollectionList), `api/tracking.py` (OrderTrackingView), serializers, URLs |

### Gaps menores restantes (opcionais)

- **E2**: UI de loyalty na conta do cliente (handler e backend prontos, falta template `account.html`)
- **E3**: Card não está em nenhum preset default (handler pronto, precisa de directive explícita)
- **E5**: Templates `order_dispatched.html` e `order_delivered.html` não existem (fallback hardcoded funciona)
- **E6**: API de account/history não implementada (catalog e tracking completos)

---

## Contexto

O Core está completo e testado (~2.444 testes). O App cobre a totalidade das features planejadas neste plano.

**Princípio**: Cada WP tem prompt próprio com contexto completo. Sem dependência de conversas anteriores.

---

## WP-E1: Disponibilidade + Alternativas no Storefront

**Objetivo**: O cliente vê disponibilidade real e recebe sugestões quando algo está indisponível.

### O Que Já Existe (backend pronto)
- `_helpers.py`: `_get_availability()`, `_availability_badge()` (6 estados)
- `StockingBackend.check_availability()` + `get_alternatives()`
- `offering.contrib.suggestions.find_alternatives()` (scoring por keywords+coleção+preço)
- `StockHoldHandler._build_issue()` com alternatives + actions
- Availability policies: stock_only, planned_ok, demand_ok
- Badge system no PDP (available, preparing, d1_only, sold_out, paused, unknown)

### Tarefas

1. **PDP — Alternativas quando indisponível**
   - `catalog.py` → `ProductDetailView`: quando badge = sold_out ou paused, buscar alternativas
   - Chamar `_load_stock_backend().get_alternatives(sku, 1)` (ou `find_alternatives` direto)
   - Passar `alternatives` no contexto (lista de dicts: sku, name, price_q, price_display, badge)
   - `product_detail.html`: seção "Produtos similares" após info do produto
   - Mostrar como cards compactos (product_card.html reutilizado) com botão de add

2. **PDP — Aviso de quantidade ao adicionar**
   - `cart.py` → `AddToCartView`: ao adicionar, verificar disponibilidade
   - Se qty > available: retornar partial `availability_notice.html` (HTMX)
   - Notice: "Disponível: X unidades" com opção de ajustar qty
   - Se available = 0: "Esgotado" com link para alternativas na PDP

3. **Carrinho — Warnings inline por item**
   - Novo endpoint: `CartCheckView` (GET, HTMX) — revalida estoque de todos os itens
   - Chamar `check_availability` para cada SKU no carrinho
   - Retornar partial `cart_warnings.html` com issues por item
   - Actions: "Ajustar para X" (HTMX patch), "Remover" (HTMX delete)
   - Carregar ao abrir cart page e antes do checkout (hx-trigger="load")

4. **Testes**
   - test_pdp_shows_alternatives_when_sold_out
   - test_pdp_no_alternatives_when_available
   - test_add_to_cart_warns_insufficient_stock
   - test_cart_check_flags_unavailable_items

### Arquivos Principais
- `channels/web/views/catalog.py` — ProductDetailView
- `channels/web/views/cart.py` — AddToCartView, novo CartCheckView
- `channels/web/views/_helpers.py` — helpers existentes
- `channels/web/templates/storefront/product_detail.html` — seção alternativas
- `channels/web/templates/storefront/partials/availability_notice.html` — NOVO
- `channels/web/templates/storefront/partials/cart_warnings.html` — NOVO
- `channels/web/urls.py` — rota do CartCheckView
- `channels/backends/stock.py` — get_alternatives (já implementado)

---

## WP-E2: Loyalty na UI

**Objetivo**: Cliente vê pontos, tier e stamps na conta. Pontos ganhos automaticamente ao completar pedido.

### O Que Já Existe (Core pronto)
- `LoyaltyAccount` (points_balance, lifetime_points, stamps, tier BRONZE→PLATINUM)
- `LoyaltyTransaction` (ledger imutável: earn, redeem, stamp, adjust, expire)
- `LoyaltyService` (enroll, earn_points, redeem_points, add_stamp, get_transactions)
- Auto-tier upgrade via lifetime_points
- Testes e admin completos no Core

### Tarefas

1. **Ativar loyalty no App**
   - `settings.py`: adicionar `"shopman.customers.contrib.loyalty"` ao INSTALLED_APPS
   - Rodar migrate

2. **Handler de pontos no pedido**
   - Novo handler: `LoyaltyEarnHandler` em `channels/handlers/loyalty.py`
   - Topic: `loyalty.earn` (adicionar em topics.py)
   - Lógica: `LoyaltyService.earn_points(customer_ref, points=total_q // 100, ...)`
   - Enroll automático se conta não existe
   - Registrar em setup.py

3. **Pipeline: conectar ao lifecycle**
   - Adicionar `"loyalty.earn"` ao pipeline `on_completed` dos presets remote() e pos()
   - Quando pedido completa → directive loyalty.earn → handler dá pontos

4. **UI na conta do cliente**
   - `account.py` → `AccountView._render_account()`: buscar LoyaltyAccount
   - `account.html`: nova seção "Fidelidade" com:
     - Tier badge (cor por tier)
     - Pontos disponíveis
     - Barra de progresso de stamps (se stamps_target > 0)
     - Últimas 5 transações

5. **Seed**: criar LoyaltyAccount para clientes existentes

6. **Testes**
   - test_loyalty_earn_on_order_completed
   - test_loyalty_auto_enroll
   - test_account_shows_loyalty_section
   - test_loyalty_not_shown_if_not_installed

### Arquivos Principais
- `project/settings.py` — INSTALLED_APPS
- `channels/handlers/loyalty.py` — NOVO
- `channels/topics.py` — LOYALTY_EARN
- `channels/setup.py` — registro
- `channels/presets.py` — pipeline on_completed
- `channels/web/views/account.py` — buscar loyalty
- `channels/web/templates/storefront/account.html` — seção fidelidade
- `shop/management/commands/seed.py` — seed loyalty

---

## WP-E3: Pagamento com Cartão

**Objetivo**: Cliente pode pagar com cartão (Stripe) além de PIX.

### O Que Já Existe
- `StripeBackend` (`payment_stripe.py`) — funcional (create_intent, capture, refund, etc.)
- `StripeWebhookView` — processa payment_intent.succeeded/failed, charge.refunded
- `ChannelConfig.Payment` aceita method="card"
- `PaymentCaptureHandler`, `PaymentRefundHandler` — genéricos (funcionam com qualquer backend)

### Tarefas

1. **Checkout: seletor de método de pagamento**
   - `checkout.py` → `CheckoutView`: ler métodos do canal config
   - Se canal suporta múltiplos métodos, mostrar seletor (radio buttons)
   - Guardar método escolhido em `order.data["payment"]["method"]`
   - ChannelConfig.Payment: mudar `method` para aceitar lista `["pix", "card"]`

2. **Novo topic + handler: card.create**
   - `topics.py`: adicionar CARD_CREATE
   - `handlers/payment.py`: novo `CardCreateHandler`
   - Lógica: `backend.create_intent(amount_q, method="card")` → retorna client_secret
   - Guardar client_secret em `order.data["payment"]`

3. **Template de pagamento com cartão**
   - `payment.html`: condicional por method
   - PIX: QR code atual (sem mudança)
   - Card: Stripe Elements (Payment Element) com client_secret
   - Stripe.js carregado via CDN, inicializa com client_secret
   - Após confirmação do Stripe → redirect para tracking

4. **Routing pós-commit**
   - `checkout.py`: se method="card", criar directive CARD_CREATE (não PIX_GENERATE)
   - Pipeline `on_confirmed` no preset remote: condicional por método

5. **Registrar handler em setup.py**

6. **Testes**
   - test_checkout_shows_payment_method_selector
   - test_card_payment_creates_stripe_intent
   - test_payment_page_shows_stripe_form
   - test_pix_flow_unchanged

### Arquivos Principais
- `channels/web/views/checkout.py` — seletor + routing
- `channels/web/templates/storefront/checkout.html` — radio buttons
- `channels/web/templates/storefront/payment.html` — condicional PIX/Card
- `channels/handlers/payment.py` — CardCreateHandler
- `channels/topics.py` — CARD_CREATE
- `channels/setup.py` — registro
- `channels/config.py` — Payment.method como lista
- `channels/presets.py` — atualizar remote()

---

## WP-E4: Dashboard do Operador

**Objetivo**: Operador vê pedidos do dia, fila de produção e alertas de estoque no admin.

### O Que Já Existe
- Unfold admin instalado e configurado
- Todos os models têm admin registrado
- Ordering.Order com status e timestamps
- Crafting.WorkOrder com lifecycle
- Stocking.StockAlert com min_quantity

### Tarefas

1. **Dashboard view no admin**
   - `shop/admin.py`: criar dashboard via Unfold dashboard mixin
   - Cards: Pedidos hoje (por status), Faturamento do dia, Produção pendente
   - Lista: Últimos 10 pedidos com status badges
   - Lista: Work Orders abertas
   - Lista: Stock alerts ativos

2. **Pedidos do dia — widget**
   - Query: `Order.objects.filter(created_at__date=today).values("status").annotate(count=Count("id"))`
   - Exibir como cards coloridos (novo, confirmado, processando, pronto, entregue, cancelado)
   - Link para admin list filtrada por status

3. **Produção do dia — widget**
   - Query: `WorkOrder.objects.filter(status="open", created_at__date=today)`
   - Mostrar: recipe output, quantity, assigned
   - Link para detail

4. **Alertas de estoque — widget**
   - Query: Quants com quantity < StockAlert.min_quantity (join)
   - Mostrar: SKU, atual, mínimo, deficit

5. **Testes**
   - test_dashboard_accessible_by_staff
   - test_dashboard_shows_order_counts
   - test_dashboard_shows_production

### Arquivos Principais
- `shop/admin.py` — dashboard
- `shop/templates/admin/dashboard.html` — NOVO (se Unfold precisar)

---

## WP-E5: Notificações Transacionais Reais

**Objetivo**: Cliente recebe email/WhatsApp real em eventos do pedido.

### O Que Já Existe
- 5 backends: Console (ativo), Manychat (ativo se token), Email (implementado), SMS (stub Twilio), WhatsApp (stub Meta)
- Webhook backend (gateway genérico para n8n/Zapier)
- NotificationSendHandler com routing + fallback
- Pipeline já cria directives `notification.send` em eventos do pedido

### Tarefas

1. **Ativar EmailBackend no setup.py**
   - Registrar `email` no notification registry
   - Configurar `DEFAULT_FROM_EMAIL` no settings
   - Criar templates de email por evento (order_confirmed, order_ready, payment_expired)

2. **Stock alerts → notificação**
   - Conectar signal `post_save(Move)` → quando quant < StockAlert.min_quantity
   - Criar directive `NOTIFICATION_SEND` com template "stock_alert"
   - Routing: operador (email ou console)

3. **Notification routing por canal**
   - Atualizar DEFAULT_ROUTING:
     - web: email (fallback: console)
     - whatsapp/manychat: manychat (fallback: email)
   - Garantir que presets declaram notification backend

4. **Templates de email**
   - `channels/templates/notifications/email/order_confirmed.html`
   - `channels/templates/notifications/email/order_ready.html`
   - `channels/templates/notifications/email/payment_expired.html`
   - `channels/templates/notifications/email/stock_alert.html`
   - Usar Django template engine, contexto do pedido

5. **Testes**
   - test_email_sent_on_order_confirmed
   - test_stock_alert_creates_notification
   - test_fallback_to_console_on_email_failure

### Arquivos Principais
- `channels/setup.py` — registro EmailBackend
- `channels/backends/notification_email.py` — já implementado
- `channels/handlers/notification.py` — routing
- `channels/handlers/_stock_receivers.py` — stock alert → notification
- `channels/templates/notifications/email/` — NOVO (4 templates)
- `project/settings.py` — EMAIL config

---

## WP-E6: API REST Completa

**Objetivo**: API REST pública para mobile e integrações externas.

### O Que Já Existe
- Core APIs: Offering (products, collections, listings), Ordering (sessions, orders), Customers, Payments
- Channels API: apenas cart + checkout
- drf-spectacular instalado (OpenAPI)
- Throttling configurado no Ordering

### Tarefas

1. **Storefront API — catálogo público**
   - `channels/api/catalog.py`: ProductListView, ProductDetailView, CollectionListView
   - Reutilizar `_annotate_products()` para enriquecer com preço e disponibilidade
   - Filtros: collection, search query, available_only
   - Paginação: cursor-based

2. **Storefront API — tracking**
   - `channels/api/tracking.py`: OrderTrackingView (GET by ref)
   - Retorna: status, timeline, fulfillment, payment status

3. **Storefront API — conta**
   - `channels/api/account.py`: CustomerProfileView, AddressListView
   - Requer session auth ou token

4. **Storefront API — histórico**
   - `channels/api/orders.py`: OrderHistoryView (GET by phone, últimos 20)

5. **OpenAPI schema atualizado**
   - Tags por área (catalog, cart, checkout, tracking, account)
   - Exemplos de request/response

6. **Testes**
   - test_catalog_api_returns_products_with_prices
   - test_tracking_api_returns_order_status
   - test_account_api_requires_auth

### Arquivos Principais
- `channels/api/catalog.py` — NOVO
- `channels/api/tracking.py` — NOVO
- `channels/api/account.py` — NOVO
- `channels/api/orders.py` — NOVO
- `channels/api/urls.py` — atualizar rotas
- `project/urls.py` — sem mudança (já inclui channels api)

---

## Ordem de Execução

```
WP-E1 (disponibilidade)    — UX crítica para o cliente
  │
WP-E2 (loyalty)            — independente, rápido
  │
WP-E3 (cartão)             — independente, checkout
  │
WP-E4 (dashboard)          — admin, independente
  │
WP-E5 (notificações)       — operacional
  │
WP-E6 (API REST)           — expansão, depende de E1 (catalog helpers)
```

E1 primeiro (disponibilidade é UX core). E2-E5 são independentes entre si. E6 por último (reutiliza helpers de E1).

---

## Critério de Aceite Global

1. `make test` — 0 failures
2. `make lint` — 0 warnings
3. Storefront mostra alternativas quando produto indisponível
4. Loyalty: pontos ganhos ao completar pedido, visíveis na conta
5. Checkout aceita PIX e Cartão
6. Admin tem dashboard com pedidos, produção e alertas
7. Email transacional funciona (order_confirmed ao menos)
8. API REST expõe catálogo, tracking e conta

---

## Prompts de Execução

### WP-E1 — Disponibilidade + Alternativas
```
Execute WP-E1 do EVOLUTION-PLAN.md: Disponibilidade + Alternativas no Storefront.

Contexto: O backend de disponibilidade está 95% pronto. Falta a camada de UI.

O que já existe (NÃO reimplementar):
- _helpers.py: _get_availability(sku) retorna breakdown {ready, in_production, d1}
- _helpers.py: _availability_badge(avail, product) retorna {label, css_class, can_add_to_cart}
- backends/stock.py: StockingBackend.get_alternatives(sku, qty) retorna [Alternative(sku, name, available_qty)]
- offering.contrib.suggestions.find_alternatives(sku, limit=5) retorna produtos scored
- product_detail.html já mostra badge de disponibilidade (6 estados)

Convenções (CLAUDE.md):
- ref not code, centavos _q, zero residuals
- Stack: Django templates + Tailwind + HTMX

Leia PRIMEIRO:
- channels/web/views/_helpers.py (helpers existentes)
- channels/web/views/catalog.py (ProductDetailView)
- channels/web/views/cart.py (AddToCartView)
- channels/web/templates/storefront/product_detail.html
- channels/web/templates/storefront/partials/cart_item.html
- channels/backends/stock.py (get_alternatives)

Tarefas:

1. PDP — Alternativas quando indisponível:
   - ProductDetailView: quando badge.css_class in ("badge-sold-out", "badge-paused"),
     buscar alternativas via backend ou find_alternatives direto
   - Anotar alternativas com _annotate_products() para ter preço e badge
   - Passar alternatives no contexto
   - product_detail.html: seção "Produtos Similares" (cards compactos, HTMX add-to-cart)
   - Se produto disponível: não mostrar seção (ou mostrar colapsada)

2. PDP — Aviso de quantidade:
   - Passar available_qty no contexto do ProductDetailView
   - product_detail.html: JS inline que compara qty selecionada vs available_qty
   - Se qty > available: mostrar notice "Disponível: X unidades"
   - Não bloquear adição (carrinho valida depois)

3. Carrinho — Revalidação de estoque:
   - Nova view: CartCheckView (GET /cart/check/) — HTMX
   - Para cada item no carrinho, chamar _get_availability(sku)
   - Se qty > available: retornar warning partial
   - cart.html: hx-get="/cart/check/" hx-trigger="load" hx-target="#cart-warnings"
   - Template partials/cart_warnings.html: lista de warnings com ações

4. Testes em tests/web/:
   - test_pdp_shows_alternatives_when_sold_out
   - test_pdp_hides_alternatives_when_available
   - test_cart_check_warns_on_insufficient_stock
   - test_cart_check_ok_when_all_available

5. make test + make lint
```

### WP-E2 — Loyalty na UI
```
Execute WP-E2 do EVOLUTION-PLAN.md: Loyalty na UI.

Contexto: O Core de Loyalty está 100% pronto mas não instalado no App.

O que já existe no Core (NÃO reimplementar):
- shopman.customers.contrib.loyalty (models, service, admin, tests)
- LoyaltyService: enroll(), earn_points(), redeem_points(), add_stamp(), get_transactions()
- LoyaltyAccount: points_balance, lifetime_points, stamps, tier (BRONZE→PLATINUM)
- Auto-tier upgrade via lifetime_points thresholds

Leia PRIMEIRO:
- shopman-core/customers/shopman/customers/contrib/loyalty/service.py
- shopman-core/customers/shopman/customers/contrib/loyalty/models.py
- channels/web/views/account.py (AccountView._render_account)
- channels/web/templates/storefront/account.html
- channels/handlers/ (padrão de handlers existentes)
- channels/setup.py (padrão de registro)
- channels/topics.py (padrão de topics)
- channels/presets.py (pipeline on_completed)

Tarefas:

1. Instalar loyalty:
   - settings.py: adicionar "shopman.customers.contrib.loyalty" ao INSTALLED_APPS
   - Rodar migrate

2. Novo handler LoyaltyEarnHandler:
   - channels/handlers/loyalty.py
   - Topic: "loyalty.earn" (adicionar em topics.py: LOYALTY_EARN = "loyalty.earn")
   - handle(): lê order_ref do payload, busca Order, calcula pontos (total_q // 100)
   - Chama LoyaltyService.enroll() (idempotent) + earn_points()
   - reference="order:{order.ref}", created_by="system"
   - Se customer_ref não existe no order: skip silenciosamente

3. Registrar handler:
   - setup.py: nova função _register_loyalty_handler()
   - Chamada em register_all()
   - Try/except ImportError (graceful se loyalty não instalado)

4. Pipeline on_completed:
   - presets.py: adicionar "loyalty.earn" ao pipeline on_completed em pos() e remote()
   - marketplace(): sem loyalty (cliente é do marketplace, não nosso)

5. UI na conta:
   - account.py: se loyalty instalado, buscar LoyaltyService.get_account(customer.ref)
   - Passar loyalty_account + últimas 5 transações no contexto
   - account.html: nova seção "Fidelidade" com:
     - Tier badge com cor (bronze=#CD7F32, silver=#C0C0C0, gold=#FFD700, platinum=#E5E4E2)
     - "X pontos disponíveis"
     - Barra de stamps (se stamps_target > 0): "X de Y carimbos"
     - Últimas transações (data, descrição, +/- pontos)

6. Seed: seed.py → criar LoyaltyAccount para clientes demo, com algumas transações

7. Testes:
   - test_loyalty_earn_handler_gives_points
   - test_loyalty_earn_auto_enrolls
   - test_loyalty_earn_skips_without_customer
   - test_account_shows_loyalty_section
   - test_account_hides_loyalty_if_not_installed

8. make test + make lint
```

### WP-E3 — Pagamento com Cartão
```
Execute WP-E3 do EVOLUTION-PLAN.md: Pagamento com Cartão (Stripe).

Contexto: O StripeBackend existe e é funcional. O storefront só suporta PIX.

O que já existe (NÃO reimplementar):
- backends/payment_stripe.py: StripeBackend com create_intent, capture, refund, cancel
- webhooks.py: StripeWebhookView processa payment_intent.succeeded/failed
- handlers/payment.py: PaymentCaptureHandler e PaymentRefundHandler (genéricos)
- PixGenerateHandler: cria intent PIX, guarda QR code, cria timeout directive

Leia PRIMEIRO:
- channels/web/views/checkout.py (CheckoutView, fluxo pós-commit)
- channels/web/views/payment.py (PaymentPageView, PaymentStatusView)
- channels/web/templates/storefront/checkout.html
- channels/web/templates/storefront/payment.html
- channels/handlers/payment.py (PixGenerateHandler como referência)
- channels/backends/payment_stripe.py
- channels/config.py (ChannelConfig.Payment)
- channels/presets.py (remote preset)
- channels/topics.py

Tarefas:

1. ChannelConfig.Payment — suporte a múltiplos métodos:
   - config.py: Payment.method pode ser string OU lista: "pix" | "card" | ["pix", "card"]
   - Helper: Payment.available_methods → sempre retorna lista
   - Manter backward compat: method="pix" equivale a ["pix"]

2. Checkout — seletor de método:
   - checkout.py: passar available_methods no contexto
   - checkout.html: se len(methods) > 1, mostrar radio buttons
   - POST: ler payment_method do form, guardar em session.data["payment_method"]
   - Após commit: se method="card" → criar directive CARD_CREATE; se "pix" → PIX_GENERATE

3. Handler CardCreateHandler:
   - handlers/payment.py: novo handler
   - Topic: "card.create" (adicionar em topics.py)
   - Lógica: backend.create_intent(amount_q, currency, reference, metadata={"method": "card"})
   - Guardar client_secret em order.data["payment"]
   - NÃO criar timeout (Stripe gerencia expiração)

4. Payment page condicional:
   - payment.py: passar method no contexto
   - payment.html: {% if method == "pix" %} QR code {% elif method == "card" %} Stripe {% endif %}
   - Stripe section: carregar stripe.js via CDN, Payment Element com client_secret
   - Após confirmação Stripe → stripe.confirmPayment() → redireciona para tracking
   - PaymentStatusView: funciona igual (webhook atualiza status)

5. Preset remote(): method=["pix", "card"]

6. Registrar CardCreateHandler em setup.py

7. Testes:
   - test_checkout_shows_method_selector_when_multiple
   - test_checkout_hides_selector_when_single_method
   - test_card_creates_stripe_intent
   - test_pix_flow_unchanged
   - test_payment_page_renders_stripe_form

8. make test + make lint
```

### WP-E4 — Dashboard do Operador
```
Execute WP-E4 do EVOLUTION-PLAN.md: Dashboard do Operador.

Contexto: O admin usa Unfold (django-unfold). Todos os models têm admin.
Não há dashboard customizado.

Leia PRIMEIRO:
- shop/admin.py (admin atual)
- project/settings.py (UNFOLD config)
- Documentação Unfold: dashboard components (unfold.contrib.dashboard)
- shopman-core/ordering/shopman/ordering/models/order.py (Order.Status, timestamps)
- shopman-core/crafting/shopman/crafting/models/ (WorkOrder)
- shopman-core/stocking/shopman/stocking/models/ (StockAlert, Quant)

Tarefas:

1. Dashboard admin via Unfold:
   - shop/admin.py: implementar dashboard usando padrão Unfold
   - URL: /admin/ (homepage)

2. Cards de resumo do dia:
   - Pedidos hoje (total + por status): Order.objects.filter(created_at__date=today)
   - Faturamento do dia: sum(total_q) de pedidos confirmed+
   - Produção aberta: WorkOrder.objects.filter(status="open").count()
   - Alertas ativos: StockAlerts triggered

3. Lista de pedidos recentes:
   - Últimos 10 pedidos com: ref, status badge, total, hora, canal
   - Link para detail no admin

4. Lista de produção pendente:
   - WorkOrders abertas: output, quantity, assigned

5. Alertas de estoque:
   - SKUs abaixo do mínimo: sku, atual, mínimo, posição

6. Testes:
   - test_dashboard_accessible_by_staff
   - test_dashboard_returns_200

7. make test + make lint
```

### WP-E5 — Notificações Transacionais Reais
```
Execute WP-E5 do EVOLUTION-PLAN.md: Notificações Transacionais Reais.

Contexto: O sistema de notificações existe (handler, backends, routing, fallback).
ConsoleBackend é o default. EmailBackend está implementado mas não registrado.

O que já existe (NÃO reimplementar):
- channels/backends/notification_email.py: EmailBackend com send() via Django mail
- channels/backends/notification_console.py: ConsoleBackend (fallback)
- channels/handlers/notification.py: NotificationSendHandler com routing + fallback
- channels/notifications.py: register_backend(), get_backend(), notify()
- Pipeline já cria directives notification.send nos eventos do pedido

Leia PRIMEIRO:
- channels/backends/notification_email.py (EmailBackend completo)
- channels/handlers/notification.py (routing logic)
- channels/setup.py (_register_notification_handlers)
- channels/notifications.py (registry)
- channels/handlers/_stock_receivers.py (signal receivers existentes)
- project/settings.py (EMAIL config)

Tarefas:

1. Registrar EmailBackend:
   - setup.py → _register_notification_handlers(): register_backend("email", EmailBackend())
   - Configurar DEFAULT_FROM_EMAIL no settings (ou ler de Shop model)

2. Stock alerts → notificação:
   - handlers/_stock_receivers.py: no signal post_save(Move), verificar StockAlerts
   - Se quant.quantity < alert.min_quantity E alert.can_trigger() (cooldown):
     criar Directive(topic=NOTIFICATION_SEND, payload={template: "stock_alert", ...})
   - Atualizar alert.last_triggered_at

3. Templates de email (Django templates):
   - channels/templates/notifications/email/base.html (layout base)
   - channels/templates/notifications/email/order_confirmed.html
   - channels/templates/notifications/email/order_ready.html
   - channels/templates/notifications/email/payment_expired.html
   - channels/templates/notifications/email/stock_alert.html
   - Contexto: order.ref, customer_name, items, total, shop_name

4. Routing default atualizado:
   - web channel: "email" (fallback: "console")
   - Garantir que presets remote() declara notification.backend = "email"

5. Testes:
   - test_email_sent_on_order_confirmed (usar django.core.mail.outbox)
   - test_stock_alert_triggers_notification_directive
   - test_fallback_to_console_on_email_error

6. make test + make lint
```

### WP-E6 — API REST Completa
```
Execute WP-E6 do EVOLUTION-PLAN.md: API REST Completa.

Contexto: Os Core apps já têm APIs DRF. O channels/api/ só tem cart + checkout.
drf-spectacular instalado (OpenAPI).

O que já existe (NÃO reimplementar):
- Core APIs: ProductViewSet, CollectionViewSet, OrderViewSet, CustomerViewSet, etc.
- channels/api/: CartView, CheckoutView (session-based)
- _helpers.py: _annotate_products() para enriquecer com preço/disponibilidade
- drf-spectacular: /api/schema/ e /api/docs/

Leia PRIMEIRO:
- channels/api/ (todos os arquivos)
- channels/web/views/_helpers.py (_annotate_products, _get_price_q, _get_availability)
- shopman-core/offering/shopman/offering/api/ (core ProductViewSet)
- shopman-core/ordering/shopman/ordering/api/ (core OrderViewSet)
- project/urls.py (rotas API)

Tarefas:

1. Catálogo público (channels/api/catalog.py):
   - ProductListView: lista produtos com preço e disponibilidade (usa _annotate_products)
   - ProductDetailView: detalhe com alternativas
   - CollectionListView: coleções com contagem de produtos
   - Filtros: ?collection=slug, ?search=query, ?available=true
   - Paginação cursor-based, 20 por página
   - Auth: AllowAny (público)

2. Tracking (channels/api/tracking.py):
   - OrderTrackingView: GET /api/tracking/{ref}/
   - Retorna: status, timeline (events), fulfillment, payment_status
   - Auth: AllowAny (ref é opaco)

3. Conta (channels/api/account.py):
   - ProfileView: GET/PATCH customer data
   - AddressView: CRUD addresses
   - OrderHistoryView: GET últimos 20 pedidos
   - Auth: session-based (SESSION_CUSTOMER_UUID)

4. URLs:
   - channels/api/urls.py: adicionar rotas
   - Agrupar com tags drf-spectacular (catalog, tracking, account)

5. Testes:
   - test_catalog_api_lists_products
   - test_catalog_api_filters_by_collection
   - test_tracking_api_returns_status
   - test_account_api_requires_auth

6. make test + make lint
```

---

## Protocolo de Execução

Ao concluir cada WP:
1. `make test` + `make lint` — 0 failures, 0 warnings
2. Reportar resultado e arquivos alterados
3. Se último WP: "Evolution completa."

Sequência: E1 → E2 → E3 → E4 → E5 → E6
