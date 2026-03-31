# PARITY-PLAN.md — Backend ↔ UI Parity

> Corrige a discrepancia entre o que o backend suporta e o que o seed + storefront + admin expoe.
> Complementar ao EVOLUTION-PLAN.md (que adiciona features novas).
> Cada WP e auto-contido, dimensionado para uma sessao do Claude Code.

---

## Status Geral

| WP | Feature | Status | Evidência |
|----|---------|--------|-----------|
| P1 | Seed Completo | Pendente | — |
| P2 | Regras de Negócio na UI | Pendente | — |
| P3 | Coupon UX | **✅ Completo** | `ApplyCouponView` + `RemoveCouponView` em cart.py, partial `coupon_section.html`, error messages, breakdown |
| P4 | Fulfillment Tracking | **✅ Completo** | `OrderTrackingView` + `OrderStatusPartialView` em tracking.py, `_carrier_tracking_url()` em _helpers.py, `_build_tracking_context()`, template com delivery/pickup/timeline |
| P5 | Admin Review | Pendente | — |

---

## Contexto

O backend evoluiu muito (handlers, backends, modifiers, validators), mas:

1. **Seed incompleto**: nao cria promotions, coupons, fulfillments, payments, enderecos
2. **UI nao reflete regras de negocio**: horario comercial, pedido minimo, happy hour, cutoff times
3. **Storefront estagnado**: loyalty so mostra saldo, retornos zero UI, promotions invisiveis

Este plano **nao adiciona features novas** — apenas faz o que ja existe aparecer corretamente.

**Principio**: Cada WP tem prompt proprio com contexto completo. Sem dependencia de conversas anteriores.

---

## WP-P1: Seed Completo — Promotions, Coupons, Payments, Fulfillments

**Objetivo**: Ao rodar `make seed`, o banco reflete TODAS as features do sistema, permitindo testar qualquer fluxo no admin e storefront.

### O Que Falta no Seed Atual
- Zero Promotions/Coupons (modelo existe, admin configurado, nada para testar)
- Zero PaymentIntent/PaymentTransaction (pedidos sem historico de pagamento)
- Zero Fulfillment/FulfillmentItem (tracking vazio em todos os pedidos)
- Zero Directive (pipeline nunca executado pelo seed)
- Zero CustomerAddress (checkout de delivery incompleto)
- Loyalty so parcialmente criado (3 contas, sem transacoes variadas)

### Tarefas

1. **Promotions e Coupons**
   - Criar 2 promotions ativas:
     - "Semana do Pao": 15% off em produtos da colecao Paes Artesanais, validade 7 dias
     - "Inaugura Delivery": frete gratis (ou desconto fixo R$5) no canal delivery
   - Criar 3 coupons:
     - "NELSON10": 10% off, uso unico, valido 30 dias
     - "PRIMEIRACOMPRA": R$5 off em pedidos acima de R$30, uso unico
     - "FUNCIONARIO": 20% off, uso ilimitado, restrito ao grupo "staff"

2. **CustomerAddress para clientes existentes**
   - Adicionar 1-2 enderecos para cada cliente (CLI-001 a CLI-007)
   - Um endereco marcado como default
   - Dados realistas de SP/RJ

3. **PaymentIntent + PaymentTransaction para pedidos existentes**
   - Para cada pedido com status completed/delivered: criar PaymentIntent (status=captured)
   - Criar PaymentTransaction correspondente (amount_q = order.total_q)
   - Metodo: PIX para 70%, card para 30% dos pedidos
   - Gateway ref: gerar UUID como simulacao

4. **Fulfillment para pedidos entregues/completos**
   - Para pedidos com status delivered/completed:
     - Criar Fulfillment (type=delivery ou pickup conforme canal)
     - Para delivery: tracking_code aleatorio, carrier="correios"
   - Para pedidos com status processing: fulfillment sem tracking (em preparacao)

5. **Directives para pedidos existentes**
   - Para cada pedido, criar directives refletindo o pipeline executado:
     - stock.hold, payment.capture, notification.send, fulfillment.create
     - Status: completed (para pedidos finalizados)

6. **Loyalty enriquecido**
   - Mais transacoes para os 3 clientes com loyalty:
     - Earn por pedido (1 ponto por R$1), redeem ocasional, stamps
   - Adicionar mais 2 clientes com loyalty ativo

7. `make test` + `make lint`

### Arquivos Principais
- `shop/management/commands/seed.py` — 6 novas funcoes _seed_*
- `shop/models.py` — importar Promotion, Coupon (se necessario)

---

## WP-P2: Storefront — Visibilidade de Regras de Negocio

**Objetivo**: A storefront comunica proativamente horario de funcionamento, pedido minimo, cutoff de entrega e promotions ativas — em vez de so mostrar erros no checkout.

### O Que Existe Mas Nao Aparece
- `BusinessHoursValidator`: valida se loja esta aberta, mas UI nao mostra horario
- `MinimumOrderValidator`: valida pedido minimo, mas UI nao avisa
- `Shop.opening_hours`: dados existem no banco (seed cria)
- `Promotion` model: promocoes existem (apos WP-P1) mas nada as exibe
- Cutoff de pre-encomenda (18h): so aparece como erro no checkout

### Tarefas

1. **Banner de horario/status da loja**
   - `_helpers.py`: novo helper `_shop_status()` retorna {is_open, opens_at, closes_at, message}
   - Ler `Shop.opening_hours` e comparar com `timezone.localtime().time()`
   - Se fechado: "Abrimos as Xh" | Se fecha em < 1h: "Fechamos as Xh"
   - `base.html` ou header: banner condicional (HTMX ou context processor)

2. **Aviso de pedido minimo no carrinho**
   - `cart.py` → `CartView.get()`: calcular total do carrinho vs minimum_order
   - Ler minimum de `channel.config` (se existir) ou `Shop.defaults`
   - Se total < minimo: badge "Faltam R$X para o pedido minimo"
   - `cart.html`: condicional antes do botao de checkout

3. **Cutoff de entrega proativo**
   - `checkout.html`: se canal suporta pre-encomenda, mostrar info:
     - "Pedidos ate 18h para entrega amanha"
     - Se apos cutoff: "Proxima entrega: depois de amanha"
   - Ler cutoff_hour de `channel.config.preorder`

4. **Promotions ativas no catalogo**
   - `catalog.py` → `MenuView`: buscar Promotion.objects.active() (ou filter por data)
   - Passar promotions no contexto
   - `menu.html`: banner/card de promocoes ativas acima da lista de produtos
   - Cada promocao: nome, descricao curta, badge de desconto

5. **Badge de desconto no produto**
   - Se produto esta em uma promotion ativa: badge "X% OFF" no card
   - `_annotate_products()`: enriquecer com promotion info (se existir)
   - `product_card.html`: badge condicional

6. **Testes**
   - test_shop_status_shows_open_hours
   - test_cart_shows_minimum_order_warning
   - test_menu_shows_active_promotions
   - test_product_card_shows_discount_badge

7. `make test` + `make lint`

### Arquivos Principais
- `channels/web/views/_helpers.py` — _shop_status(), enriquecer _annotate_products()
- `channels/web/views/catalog.py` — MenuView busca promotions
- `channels/web/views/cart.py` — CartView checa pedido minimo
- `channels/web/templates/storefront/menu.html` — banner promotions
- `channels/web/templates/storefront/cart.html` — badge pedido minimo
- `channels/web/templates/storefront/checkout.html` — info cutoff
- `channels/web/templates/storefront/partials/product_card.html` — badge desconto

---

## WP-P3: Storefront — Coupon UX + Feedback Visual

**Objetivo**: O fluxo de cupom funciona end-to-end com feedback visual claro.

### O Que Existe
- `ApplyCouponView` em `cart.py` (POST aplica cupom ao carrinho)
- `RemoveCouponView` em `cart.py` (POST remove cupom)
- `CouponModifier` em `shop/modifiers.py` (aplica desconto no pricing)
- Modelo Coupon com validacoes (validade, uso unico, grupo restrito, min order)

### O Que Falta
- Campo de input de cupom no carrinho (template)
- Feedback visual: cupom aplicado, desconto visivel, erro se invalido
- Breakdown de preco: subtotal, desconto do cupom, total

### Tarefas

1. **Input de cupom no carrinho**
   - `cart.html`: formulario HTMX com input text + botao "Aplicar"
   - hx-post="/cart/coupon/apply/" hx-target="#coupon-feedback"
   - Se ja tem cupom aplicado: mostrar badge com nome + botao "Remover"

2. **Feedback HTMX de cupom**
   - `ApplyCouponView`: retornar partial com resultado
   - Sucesso: "Cupom NELSON10 aplicado! -10%"
   - Erro: mensagem clara ("Cupom expirado", "Pedido minimo nao atingido", etc.)
   - Partial: `partials/coupon_feedback.html`

3. **Breakdown de preco no carrinho**
   - `cart.html`: mostrar subtotal, desconto (se houver), total
   - Se cupom aplicado: linha "Desconto (NELSON10): -R$X,XX"
   - `cart.py` → `CartView.get()`: calcular e passar breakdown no contexto

4. **Breakdown no checkout**
   - `checkout.html`: mesma logica de breakdown
   - Cupom visivel mas nao editavel no checkout (editar so no carrinho)

5. **Testes**
   - test_cart_shows_coupon_input
   - test_apply_coupon_shows_discount
   - test_apply_invalid_coupon_shows_error
   - test_remove_coupon_clears_discount
   - test_checkout_shows_price_breakdown

6. `make test` + `make lint`

### Arquivos Principais
- `channels/web/views/cart.py` — ApplyCouponView feedback, CartView breakdown
- `channels/web/templates/storefront/cart.html` — input, breakdown, feedback
- `channels/web/templates/storefront/partials/coupon_feedback.html` — NOVO
- `channels/web/templates/storefront/checkout.html` — breakdown

---

## WP-P4: Storefront — Fulfillment Tracking Completo

**Objetivo**: Pagina de tracking mostra fulfillment real com transportadora, codigo de rastreio e link.

### O Que Existe
- `tracking.py` → `OrderTrackingView`: mostra status + timeline de eventos
- `Fulfillment` model: type, status, tracking_code, carrier, shipped_at, delivered_at
- `FulfillmentCreateHandler`, `FulfillmentUpdateHandler`
- Template `tracking.html` mostra status basico

### O Que Falta
- Template nao exibe tracking_code, carrier, link de rastreio
- Timeline nao inclui eventos de fulfillment (shipped, delivered)
- Sem indicacao visual de tipo (pickup vs delivery)

### Tarefas

1. **Carregar fulfillment na view de tracking**
   - `tracking.py`: buscar Fulfillment relacionado ao pedido
   - Passar fulfillment no contexto (com items se existirem)
   - Se delivery: tracking_code, carrier, carrier_url
   - Se pickup: estimativa de quando estara pronto

2. **Carrier URL helper**
   - `_helpers.py`: `_carrier_tracking_url(carrier, tracking_code)` → URL
   - Carriers conhecidos: correios, jadlog, loggi, motoboy (sem URL)
   - Retorna URL de rastreio ou None

3. **Template tracking enriquecido**
   - `tracking.html`:
     - Secao "Entrega" (se delivery): transportadora, codigo, link "Rastrear"
     - Secao "Retirada" (se pickup): endereco da loja, horario
     - Timeline enriquecida: incluir shipped_at, delivered_at como marcos

4. **Eventos de fulfillment na timeline**
   - Merge OrderEvent + fulfillment timestamps em timeline unificada
   - Ordenar cronologicamente
   - Cada evento: icone, label, data/hora

5. **Testes**
   - test_tracking_shows_carrier_and_code
   - test_tracking_shows_carrier_link
   - test_tracking_pickup_shows_store_address
   - test_tracking_timeline_includes_fulfillment_events

6. `make test` + `make lint`

### Arquivos Principais
- `channels/web/views/tracking.py` — carregar fulfillment
- `channels/web/views/_helpers.py` — _carrier_tracking_url()
- `channels/web/templates/storefront/tracking.html` — secoes delivery/pickup + timeline

---

## WP-P5: Admin — Promotions, Coupons e Dados Visiveis

**Objetivo**: Admin mostra todos os dados que o seed cria. Operador consegue criar/editar promotions e coupons facilmente.

### O Que Ja Existe
- Promotion e Coupon registrados em shop/admin.py (com inlines e filtros)
- Todos os models de Ordering, Stocking, Crafting, Customers com admin

### O Que Pode Estar Faltando
- Admin de Promotion/Coupon pode nao ter preview de impacto
- Fulfillment pode nao ter link para tracking externo
- Payment pode nao ter resumo legivel

### Tarefas

1. **Revisar admin de Promotion**
   - Verificar: list_display inclui status (ativa/inativa), datas, desconto
   - Adicionar: indicador visual de "ativa agora" vs "futura" vs "expirada"
   - Filtros: por status (ativa, futura, expirada), por colecao

2. **Revisar admin de Coupon**
   - Verificar: uso atual vs limite, status (ativo/usado/expirado)
   - list_display: ref, promotion, used/limit, expires_at, is_valid

3. **Fulfillment no admin de Order**
   - Se Order admin nao tem inline de Fulfillment: adicionar
   - Mostrar: status, tracking_code, carrier, shipped_at
   - Link externo para tracking da transportadora

4. **Payment no admin de Order**
   - Se Order admin nao tem inline de PaymentIntent: adicionar
   - Mostrar: status, method, amount_q (formatado), gateway_ref

5. **Dashboard (shop/dashboard.py) — verificar dados**
   - Se dashboard existe: verificar que usa dados reais do seed
   - Se widgets estao vazios: corrigir queries

6. **Testes**
   - test_promotion_admin_shows_status
   - test_order_admin_shows_fulfillment
   - test_order_admin_shows_payment

7. `make test` + `make lint`

### Arquivos Principais
- `shop/admin.py` — Promotion, Coupon admin
- `shopman-core/ordering/shopman/ordering/admin.py` — Order inlines
- `shop/dashboard.py` — verificar queries

---

## Ordem de Execucao

```
WP-P1 (seed completo)       — PRIMEIRO: sem dados, nada mais funciona
  |
WP-P2 (regras de negocio)   — storefront mostra o que existe
  |
WP-P3 (coupon UX)           — depende de P1 (coupons no seed)
  |
WP-P4 (fulfillment)         — depende de P1 (fulfillments no seed)
  |
WP-P5 (admin review)        — depende de P1 (dados para visualizar)
```

P1 e obrigatorio primeiro. P2-P5 sao independentes entre si (podem ser paralelos).

---

## Relacao com EVOLUTION-PLAN.md

Este plano **nao conflita** com o Evolution Plan:

| PARITY-PLAN | EVOLUTION-PLAN | Relacao |
|-------------|----------------|---------|
| WP-P1 (seed) | — | Complementar: seed enriquece teste de tudo |
| WP-P2 (regras) | WP-E1 (disponibilidade) | Complementar: P2=regras existentes, E1=feature nova |
| WP-P3 (coupon) | — | Novo: coupon UX nunca foi planejado |
| WP-P4 (fulfillment) | — | Novo: tracking visual nunca foi planejado |
| WP-P5 (admin) | WP-E4 (dashboard) | Complementar: P5=review, E4=dashboard novo |

**Sugestao de sequencia global**: P1 → P2 → E1 → P3 → P4 → E2 → E3 → P5/E4 → E5 → E6

---

## Prompts de Execucao

### WP-P1 — Seed Completo
```
Execute WP-P1 do PARITY-PLAN.md: Seed Completo.

Contexto: O seed atual (seed.py) cria produtos, estoque, receitas, clientes,
canais e pedidos. Mas NAO cria promotions, coupons, payments, fulfillments,
enderecos de clientes nem directives. Isso torna impossivel testar esses fluxos.

Leia PRIMEIRO:
- shop/management/commands/seed.py (inteiro — entender o padrao)
- shop/models.py (Promotion, Coupon — campos e validacoes)
- shopman-core/ordering/shopman/ordering/models/ (Fulfillment, Directive)
- shopman-core/payments/shopman/payments/models/ (PaymentIntent, PaymentTransaction)
- shopman-core/customers/shopman/customers/models/ (CustomerAddress)
- channels/topics.py (topics existentes para directives)
- channels/presets.py (pipelines para saber quais directives criar)

Convencoes (CLAUDE.md):
- ref not code, centavos _q, zero residuals

Tarefas:

1. Promotions (2):
   - "Semana do Pao": discount_type="percentage", discount_value=15,
     aplica na colecao "paes-artesanais", validade: hoje a hoje+7
   - "Delivery Desconto": discount_type="fixed", discount_value_q=500,
     aplica no canal "delivery", validade: hoje a hoje+30
   - Consultar shop/models.py para campos exatos do modelo Promotion

2. Coupons (3):
   - "NELSON10": 10% off, max_uses=1, expires_at=hoje+30
   - "PRIMEIRACOMPRA": R$5 off (fixed, 500), min_order_q=3000, max_uses=1
   - "FUNCIONARIO": 20% off, max_uses=0 (ilimitado), customer_group="staff"
   - Associar cada coupon a uma promotion (ou standalone se modelo permite)

3. CustomerAddress (1-2 por cliente):
   - CLI-001 a CLI-007: enderecos realistas de SP
   - Um default por cliente
   - Campos: street, number, complement, neighborhood, city, state, postal_code

4. PaymentIntent + PaymentTransaction para pedidos existentes:
   - Iterar pedidos com status in (completed, delivered)
   - Criar PaymentIntent: status="captured", method="pix" (70%) ou "card" (30%)
   - Criar PaymentTransaction: amount_q=order.total_q, type="capture"
   - Consultar models para campos exatos

5. Fulfillment para pedidos:
   - Pedidos delivered: Fulfillment(status="delivered", type="delivery",
     tracking_code=f"BR{random}", carrier="correios", shipped_at, delivered_at)
   - Pedidos completed (pickup): Fulfillment(status="completed", type="pickup")
   - Pedidos processing: Fulfillment(status="processing", type conforme canal)

6. Directives para pedidos:
   - Para cada pedido, criar 2-4 directives refletindo o pipeline:
     stock.hold, payment.capture, notification.send
   - Status: completed para pedidos finalizados
   - Consultar topics.py para nomes de topicos corretos

7. Loyalty enriquecido:
   - Mais transacoes earn (1 ponto por R$1 do pedido) para CLI-001, CLI-003, CLI-005
   - Adicionar loyalty para CLI-002 e CLI-004 (enroll + earn)
   - 1 transacao redeem para CLI-001 (resgatou 100 pontos)

8. Manter idempotencia: todo _seed_* deve ser seguro para re-rodar
   - Usar get_or_create ou verificar existencia antes de criar

9. make test + make lint

Resultado esperado: apos `make seed`, admin mostra promotions, coupons,
fulfillments, payments. Storefront mostra tracking completo, cupons aplicaveis.
```

### WP-P2 — Visibilidade de Regras de Negocio
```
Execute WP-P2 do PARITY-PLAN.md: Visibilidade de Regras de Negocio no Storefront.

Contexto: O backend tem validators e modifiers que aplicam regras de negocio
(horario comercial, pedido minimo, cutoff de entrega, promotions), mas a UI
nao comunica nenhuma dessas regras proativamente. O cliente so descobre quando
recebe um erro no checkout.

O que ja existe (NAO reimplementar):
- shop/validators.py: BusinessHoursValidator, MinimumOrderValidator
- shop/modifiers.py: PromotionModifier, HappyHourModifier
- Shop.opening_hours: dict com horarios por dia da semana (seed cria)
- Promotion model com datas de validade e descontos
- Channel.config com preorder_min_quantity e cutoff settings

Leia PRIMEIRO:
- shop/validators.py (BusinessHoursValidator, MinimumOrderValidator)
- shop/modifiers.py (PromotionModifier)
- shop/models.py (Shop — opening_hours, defaults; Promotion — campos)
- channels/web/views/_helpers.py (helpers existentes)
- channels/web/views/catalog.py (MenuView, ProductDetailView)
- channels/web/views/cart.py (CartView)
- channels/web/templates/storefront/ (templates atuais)
- channels/config.py (ChannelConfig — preorder config)

Convencoes (CLAUDE.md):
- ref not code, centavos _q, zero residuals
- Stack: Django templates + Tailwind + HTMX
- Nao inventar features — apenas expor o que ja existe

Tarefas:

1. Helper _shop_status():
   - channels/web/views/_helpers.py
   - Ler Shop.objects.first().opening_hours
   - Comparar com timezone.localtime() (dia da semana + hora)
   - Retornar dict: {is_open, current_day, opens_at, closes_at, message}
   - Mensagens: "Aberto ate Xh" | "Fechado — abrimos as Xh" | "Fechado hoje"

2. Banner de status no header:
   - Incluir _shop_status() no contexto das views principais (ou context processor)
   - Template: banner sutil no topo (verde=aberto, vermelho=fechado)
   - Texto: mensagem do helper
   - Nao bloquear navegacao (loja fechada = pode ver menu, nao pode fazer pedido)

3. Aviso de pedido minimo no carrinho:
   - cart.py → CartView: ler minimum_order do channel config ou Shop defaults
   - Se total < minimo: passar warning no contexto
   - cart.html: badge "Faltam R$X,XX para o pedido minimo de R$Y,YY"
   - Desabilitar botao de checkout se abaixo do minimo

4. Cutoff de entrega no checkout:
   - checkout.py: ler cutoff_hour do channel config (se preorder)
   - Passar cutoff_info no contexto
   - checkout.html: info "Pedidos ate Xh para entrega amanha"
   - Se apos cutoff: "Proxima entrega disponivel: [data]"

5. Promotions ativas no catalogo:
   - catalog.py → MenuView: Promotion.objects.filter(active, dentro da validade)
   - Passar promotions no contexto
   - menu.html: cards/banners de promotions acima da lista de produtos
   - Cada card: nome, descricao curta, porcentagem/valor do desconto

6. Badge de desconto no card de produto:
   - _annotate_products(): verificar se produto esta coberto por promotion ativa
   - Se sim: adicionar promo_badge ao dict do produto
   - product_card ou menu.html: badge "X% OFF" sobre o card

7. Testes:
   - test_shop_status_open (mock timezone para horario comercial)
   - test_shop_status_closed (mock timezone para fora do horario)
   - test_cart_minimum_order_warning (total abaixo do minimo)
   - test_cart_no_warning_above_minimum
   - test_menu_shows_active_promotions (promotion ativa no contexto)
   - test_menu_hides_expired_promotions

8. make test + make lint
```

### WP-P3 — Coupon UX + Feedback Visual
```
Execute WP-P3 do PARITY-PLAN.md: Coupon UX + Feedback Visual.

Contexto: O sistema de cupons existe end-to-end (modelo, modifier, views de
apply/remove). Mas a UI nao tem campo de input para cupom, nao mostra feedback
de aplicacao, e nao exibe breakdown de preco com desconto.

Pre-requisito: WP-P1 deve estar completo (cupons existem no seed).

O que ja existe (NAO reimplementar):
- shop/models.py: Coupon (ref, discount_type, discount_value, max_uses, expires_at, etc.)
- shop/modifiers.py: CouponModifier (aplica desconto no pricing pipeline)
- channels/web/views/cart.py: ApplyCouponView (POST), RemoveCouponView (POST)
- channels/web/urls.py: rotas /cart/coupon/apply/ e /cart/coupon/remove/

Leia PRIMEIRO:
- shop/models.py (Coupon — campos, validacoes, metodos)
- shop/modifiers.py (CouponModifier — como aplica desconto)
- channels/web/views/cart.py (ApplyCouponView, RemoveCouponView, CartView)
- channels/web/templates/storefront/cart.html (template atual)
- channels/web/templates/storefront/checkout.html (template atual)
- channels/web/urls.py (rotas existentes)

Convencoes:
- ref not code, centavos _q, Stack: Django templates + Tailwind + HTMX

Tarefas:

1. Input de cupom no carrinho:
   - cart.html: formulario HTMX abaixo dos itens, acima do total
   - Input text placeholder="Codigo do cupom" + botao "Aplicar"
   - hx-post="/cart/coupon/apply/" hx-target="#coupon-section" hx-swap="outerHTML"
   - Se ja tem cupom: mostrar badge "NELSON10 aplicado" + botao "Remover"
   - Remover: hx-post="/cart/coupon/remove/" hx-target="#coupon-section" hx-swap="outerHTML"

2. Feedback visual (partial HTMX):
   - ApplyCouponView: se sucesso, retornar partial com cupom aplicado + desconto
   - Se erro: retornar partial com mensagem de erro (vermelho)
   - Erros claros: "Cupom nao encontrado", "Cupom expirado", "Pedido minimo: R$X",
     "Cupom ja utilizado", "Cupom restrito (voce nao pertence ao grupo)"
   - Template: partials/coupon_section.html (estado aplicado ou input vazio)

3. Breakdown de preco no carrinho:
   - CartView.get(): calcular subtotal, desconto (se cupom), total
   - Passar breakdown dict no contexto
   - cart.html: tabela de totais:
     - Subtotal: R$XX,XX
     - Desconto (CUPOM): -R$X,XX (se aplicavel, cor verde)
     - Total: R$XX,XX (bold)

4. Breakdown no checkout:
   - checkout.html: repetir breakdown (readonly)
   - Mostrar cupom aplicado mas sem opcao de editar (editar = voltar ao carrinho)

5. Testes:
   - test_cart_shows_coupon_input_field
   - test_apply_valid_coupon_shows_discount (POST + verifica partial)
   - test_apply_invalid_coupon_shows_error_message
   - test_remove_coupon_clears_discount_and_shows_input
   - test_cart_breakdown_with_coupon
   - test_cart_breakdown_without_coupon
   - test_checkout_shows_readonly_breakdown

6. make test + make lint
```

### WP-P4 — Fulfillment Tracking Completo
```
Execute WP-P4 do PARITY-PLAN.md: Fulfillment Tracking Completo.

Contexto: A pagina de tracking mostra status do pedido e timeline de eventos,
mas nao exibe informacoes de fulfillment (transportadora, codigo de rastreio,
link externo). Apos WP-P1, fulfillments existem no banco.

Pre-requisito: WP-P1 deve estar completo (fulfillments existem no seed).

O que ja existe (NAO reimplementar):
- channels/web/views/tracking.py: OrderTrackingView (GET)
- channels/web/templates/storefront/tracking.html: status + timeline
- shopman-core/ordering/shopman/ordering/models/fulfillment.py: Fulfillment model
- handlers/fulfillment.py: FulfillmentCreateHandler, FulfillmentUpdateHandler

Leia PRIMEIRO:
- channels/web/views/tracking.py (view completa)
- channels/web/templates/storefront/tracking.html (template atual)
- shopman-core/ordering/shopman/ordering/models/fulfillment.py (Fulfillment campos)
- channels/web/views/_helpers.py (helpers existentes)

Convencoes:
- ref not code, centavos _q, Stack: Django templates + Tailwind + HTMX

Tarefas:

1. Carregar fulfillment na view:
   - tracking.py: buscar Fulfillment.objects.filter(order=order).first()
   - Se existe: passar fulfillment no contexto
   - Incluir FulfillmentItems se existirem

2. Carrier URL helper:
   - _helpers.py: _carrier_tracking_url(carrier, tracking_code)
   - Mapa de carriers:
     - "correios": f"https://rastreamento.correios.com.br/?objetos={code}"
     - "jadlog": f"https://www.jadlog.com.br/tracking?code={code}"
     - "loggi": None (sem tracking publico)
     - default: None
   - Retorna URL string ou None

3. Secao de entrega no template:
   - tracking.html: nova secao "Entrega" ou "Retirada"
   - Se delivery:
     - Transportadora: nome
     - Codigo de rastreio: code (copiavel)
     - Botao "Rastrear" → link externo (se carrier URL disponivel)
     - Status: "em transito" / "entregue" / "aguardando envio"
   - Se pickup:
     - Endereco da loja (ler de Shop model)
     - Horario de funcionamento
     - Status: "pronto para retirada" / "em preparacao"

4. Timeline unificada:
   - Merge OrderEvents + fulfillment timestamps (shipped_at, delivered_at)
   - Ordenar cronologicamente
   - Cada entry: {icon, label, datetime, description}
   - Icons sugeridos: pedido, confirmado, preparando, enviado, entregue

5. Testes:
   - test_tracking_shows_delivery_carrier_and_code (fulfillment delivery)
   - test_tracking_shows_carrier_link (correios)
   - test_tracking_no_link_for_unknown_carrier
   - test_tracking_pickup_shows_store_info
   - test_tracking_timeline_includes_shipped_event

6. make test + make lint
```

### WP-P5 — Admin Review
```
Execute WP-P5 do PARITY-PLAN.md: Admin Review — Promotions, Fulfillments, Payments visiveis.

Contexto: Apos WP-P1 (seed completo), o banco tem promotions, coupons,
fulfillments e payments. Precisamos verificar que o admin exibe tudo
corretamente e fazer ajustes onde necessario.

Pre-requisito: WP-P1 completo.

Leia PRIMEIRO:
- shop/admin.py (Promotion, Coupon admin — ja registrados)
- shopman-core/ordering/shopman/ordering/admin.py (Order admin — inlines existentes)
- shopman-core/payments/shopman/payments/admin.py (PaymentIntent, PaymentTransaction)
- shop/dashboard.py (dashboard existente)

Convencoes:
- ref not code, centavos _q

Tarefas:

1. Promotion admin:
   - Verificar list_display: deve incluir nome, discount, datas, status calculado
   - Adicionar metodo is_active_now() como coluna boolean
   - Filtro por status: "Ativa", "Futura", "Expirada" (list_filter com custom filter)
   - Se ja esta bom: nao mexer

2. Coupon admin:
   - Verificar list_display: ref, promotion, uses_count/max_uses, expires_at, is_valid
   - Adicionar coluna usage_display (ex: "3/10 usos" ou "ilimitado")
   - Se ja esta bom: nao mexer

3. Order admin — inlines de Fulfillment e Payment:
   - Verificar se FulfillmentInline esta no OrderAdmin
   - Se NAO: adicionar FulfillmentInline (readonly, mostra status, tracking, carrier)
   - Verificar se PaymentIntentInline esta no OrderAdmin
   - Se NAO: adicionar inline (readonly, mostra status, method, amount)
   - Considerar que OrderAdmin esta no core (ordering/admin.py) — pode ser necessario
     registrar inlines de apps diferentes via unregister/re-register

4. Dashboard (shop/dashboard.py):
   - Verificar que widgets mostram dados reais do seed
   - Se algum widget esta vazio ou com query incorreta: corrigir
   - Verificar: pedidos do dia, faturamento, producao pendente, alertas de estoque

5. Testes:
   - test_promotion_admin_list_displays_status
   - test_order_admin_shows_fulfillment_inline
   - test_order_admin_shows_payment_inline
   - test_dashboard_returns_200

6. make test + make lint
```

---

## Criterio de Aceite Global

1. `make seed` → banco com promotions, coupons, addresses, payments, fulfillments
2. Admin: promotions com status, orders com fulfillment e payment inlines
3. Storefront: horario da loja visivel, pedido minimo avisado, promotions no catalogo
4. Storefront: cupom aplicavel com feedback, breakdown de preco
5. Storefront: tracking com transportadora e codigo de rastreio
6. `make test` — 0 failures
7. `make lint` — 0 warnings

---

## Protocolo de Execucao

Ao concluir cada WP:
1. `make test` + `make lint` — 0 failures, 0 warnings
2. Reportar resultado e arquivos alterados
3. Se ultimo WP: "Parity completa."

Sequencia: P1 → P2 → P3 → P4 → P5
