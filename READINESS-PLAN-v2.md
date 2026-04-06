# READINESS-PLAN v2 — Production-Ready

> Plano de ação pós-auditoria 2026-04-06. WPs autocontidas com prompts.
> Cada WP tem: objetivo, escopo, critério de done, e prompt para execução.

---

## Visão Geral

```
P0 — Bloqueantes              WP-R1 a WP-R5   (sem esses, não vai a produção)
P1 — Customer Experience      WP-R6 a WP-R10  (explorar o backend que já existe)
P2 — POS Production-Ready     WP-R11 a WP-R16 (operação diária real)
P3 — Robustez                 WP-R17 a WP-R20 (resiliência e testes)
```

---

## P0 — BLOQUEANTES PARA PRODUÇÃO

### WP-R1: Delivery — Taxa de Entrega + Zona

**Objetivo:** Delivery real requer taxa e zona. Hoje aceita qualquer CEP, grátis.

**Escopo:**
- Modelo `DeliveryZone` no framework (bairros ou faixas de CEP → taxa fixa em _q)
- Configurável via admin (Shop ou Channel level)
- Modifier `DeliveryFeeModifier` (order 70, após employee/happyhour) que adiciona `delivery_fee_q` ao session.data e ao total
- Validação no checkout: se delivery e endereço fora de todas as zonas → erro "Não entregamos neste endereço"
- Exibição no cart/checkout: linha "Taxa de entrega: R$ X,XX" (ou "Grátis" se 0)
- CommitService propaga `delivery_fee_q` para order.data

**Done:** Checkout com delivery mostra taxa, bloqueia CEPs fora da zona, taxa aparece no tracking.

**Prompt:**
```
Implementar taxa de entrega e zona de entrega para o Django Shopman.

CONTEXTO:
- Hoje o checkout aceita qualquer endereço sem taxa. Isso não é viável para produção.
- O checkout já coleta endereço estruturado via Google Places + CEP (ver checkout_address.html).
- Os campos addr_postal_code, addr_neighborhood, addr_city estão disponíveis no POST.
- Modifiers existentes em shopman/modifiers.py seguem padrão: order numérica, recebem session, retornam ops.
- CommitService copia chaves explícitas de session.data → order.data.

TAREFAS:
1. Criar modelo DeliveryZone em shopman/models/ com: name, zone_type (cep_prefix | neighborhood | city),
   match_value (ex: "860" para CEPs 860xx), fee_q (centavos), is_active, sort_order.
   Admin inline no ShopAdmin.

2. Criar DeliveryFeeModifier (order=70) em shopman/modifiers.py:
   - Se fulfillment_type != "delivery" → skip
   - Ler addr_postal_code e addr_neighborhood de session.data
   - Buscar DeliveryZone ativa que matche (cep_prefix first, neighborhood fallback)
   - Se nenhuma zona → set session.data["delivery_zone_error"] = True
   - Se zona encontrada → set session.data["delivery_fee_q"] = zone.fee_q
   - Incluir delivery_fee_q no session total (via set_data op)

3. Checkout validation: se delivery e delivery_zone_error → erro "Não entregamos neste endereço ainda"

4. Template: mostrar linha de taxa no cart drawer, checkout summary, e tracking.
   Se fee_q == 0, mostrar "Entrega grátis".

5. CommitService: adicionar delivery_fee_q à lista de chaves propagadas em _do_commit().

6. Testes: zona match por CEP prefix, zona match por bairro, fora de zona (erro), taxa 0 (grátis),
   propagação para order.data.

7. Migration + seed com zonas de exemplo para Nelson.

Convenções: _q para centavos, ref not code, zero residuals.
Consultar docs/reference/data-schemas.md para chaves existentes em session.data e order.data.
```

---

### WP-R2: Pagamento com Cartão (Stripe)

**Objetivo:** Ativar pagamento com cartão. Backend + frontend já estão 95% prontos.

**Escopo:**
- `STRIPE_PUBLISHABLE_KEY` no settings + context_processor → meta tag no base.html
- `payment.initiate()` já roteia para `payment_stripe.create_intent()` que retorna `client_secret`
- Template `payment.html` já tem branch `method == "card"` com Stripe Elements
- Falta: meta tag, key no .env, CSP para js.stripe.com, e teste E2E

**Done:** Checkout com `payment_method: card` → Stripe Elements → pagamento confirmado → tracking.

**Prompt:**
```
Ativar pagamento com cartão (Stripe) no storefront do Django Shopman.

CONTEXTO:
- O backend Stripe está 100% implementado:
  - shopman/adapters/payment_stripe.py: create_intent() retorna client_secret
  - shopman/services/payment.py: initiate() roteia por method, salva client_secret em order.data.payment
  - shopman/webhooks/stripe.py: StripeWebhookView processa payment_intent.succeeded
- O template payment.html JÁ TEM branch para method=="card":
  - Stripe Elements mount em #stripe-payment-element
  - submitCard() chama stripe.confirmPayment() com return_url
  - retryCard() remonta o Element
- O que falta é a meta tag com a publishable key.

TAREFAS:
1. Settings: adicionar STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

2. Context processor (context_processors.py): adicionar "stripe_publishable_key" ao contexto,
   junto com google_maps_api_key.

3. Template base.html: adicionar <meta name="stripe-publishable-key" content="{{ stripe_publishable_key }}">
   (condicional: só se stripe_publishable_key)

4. CSP (settings.py): adicionar https://js.stripe.com em script-src e connect-src,
   e https://api.stripe.com em connect-src.

5. .env.example: adicionar STRIPE_PUBLISHABLE_KEY= e STRIPE_SECRET_KEY=

6. Channel config: garantir que o canal "web" aceita method: ["pix", "card"].
   Verificar que o checkout mostra seletor quando >1 método (já implementado em _get_payment_methods).

7. Teste: criar test que verifica que payment page com method=card renderiza
   #stripe-payment-element e a meta tag. Não precisa testar Stripe real — é delegado ao Stripe.

NÃO alterar o template payment.html — já está correto. O foco é wiring (settings, context, CSP, meta).
```

---

### WP-R3: Webhook Payment Tests ✅

**Objetivo:** Garantir que PIX pago / cartão confirmado transiciona o pedido. Maior risco de produção.

**Escopo:**
- Testes para EFI webhook (PIX): signature verification, payload → payment.captured → order confirmed
- Testes para Stripe webhook: signature verification, payment_intent.succeeded → order confirmed
- Teste de idempotência: webhook duplicado não cria evento duplicado
- Teste de race: webhook chega após cancelamento → refund automático

**Done:** Webhooks testados com mock de assinatura, idempotência verificada.

**Prompt:**
```
Criar testes abrangentes para os webhooks de pagamento (Stripe e EFI/PIX) do Django Shopman.

CONTEXTO:
- shopman/webhooks/stripe.py: StripeWebhookView — recebe POST, verifica assinatura, processa evento
- shopman/webhooks/efi.py: EFI webhook — recebe notificação de PIX pago
- shopman/handlers/payment.py: processa payment.captured → transiciona order para confirmed
- shopman/flows.py: on_payment_confirmed → pode triggar refund se order já cancelled

TESTES NECESSÁRIOS:

1. Stripe webhook happy path:
   - Criar order com payment method=card, intent pending
   - POST webhook com evento payment_intent.succeeded (mock signature)
   - Verificar: intent.status == captured, order.status == confirmed, event emitido

2. EFI/PIX webhook happy path:
   - Criar order com payment method=pix, intent pending
   - POST webhook com notificação de PIX recebido
   - Verificar: intent.status == captured, order.status == confirmed

3. Idempotência:
   - Enviar mesmo webhook 2x
   - Verificar: 1 evento de payment.captured, não 2

4. Race condition — payment after cancel:
   - Criar order, cancelar
   - Webhook de pagamento chega depois
   - Verificar: refund iniciado OU OperatorAlert criado (conforme Flow.on_payment_confirmed)

5. Webhook com assinatura inválida:
   - POST com assinatura errada → 400/403

6. Webhook para order inexistente → 404 ou ignore gracioso

Usar pytest + Django TestCase. Mock das APIs externas (stripe.Webhook.construct_event, etc).
NÃO chamar APIs reais do Stripe/EFI.
```

---

### WP-R4: Counter Payment — Operador Marca Pago ✅

**Objetivo:** Pedidos balcão/POS com payment_method=counter ou dinheiro precisam que o operador marque como pago.

**Escopo:**
- Botão "Marcar como pago" no Gestor de Pedidos (pedidos/) para orders com payment counter/dinheiro
- POST endpoint que: seta order.data.payment.status = "captured", emite event, transiciona se new→confirmed
- Visível apenas para staff, com confirmação

**Done:** Operador marca pedido counter como pago, order avança normalmente.

**Prompt:**
```
Implementar marcação de pagamento para pedidos counter/dinheiro no Gestor de Pedidos.

CONTEXTO:
- Pedidos POS criam orders com payment.method = "dinheiro", "pix", ou "cartao"
- Para "dinheiro", não há gateway — o operador precisa confirmar manualmente
- O Gestor de Pedidos está em shopman/web/views/pedidos.py
- Templates em templates/pedidos/partials/card.html e detail.html
- O PedidoConfirmView já faz POST /pedidos/<ref>/confirm/ → transiciona new→confirmed

TAREFAS:
1. Novo endpoint POST /pedidos/<ref>/mark-paid/ (PedidoMarkPaidView):
   - Staff required
   - Seta order.data["payment"]["status"] = "captured"
   - Emite event payment.captured
   - Se order.status == "new" → transition to "confirmed"
   - HTMX: retorna partial atualizado do card

2. Template pedidos/partials/card.html:
   - Se payment.method in ("dinheiro", "counter") e payment.status != "captured":
     mostrar botão "Marcar Pago" (estilo success, com ícone ✓)
   - Após marcar: botão desaparece, badge "Pago" aparece

3. URL: adicionar em urls.py junto com os outros endpoints de pedidos

4. Testes: mark-paid happy path, mark-paid idempotente, mark-paid staff-only

Usar os design tokens do storefront. @click para confirmação Alpine inline ("Confirmar pagamento?").
```

---

### WP-R5: POS — Cancelamento + Erro Granular ✅

**Objetivo:** POS sem cancelamento é inoperável. Erros genéricos escondem problemas.

**Escopo:**
- Botão "Cancelar" que limpa o cart em andamento (antes de fechar)
- Botão "Cancelar Última Venda" que cancela o último order criado (se status=new, <5min)
- Erro granular: distinguir stock insuficiente, canal não configurado, validation error

**Done:** Operador pode cancelar venda em andamento e última venda fechada. Erros são claros.

**Prompt:**
```
Implementar cancelamento e erros granulares no POS do Django Shopman.

CONTEXTO:
- POS em shopman/web/views/pos.py: pos_view (GET), pos_close (POST)
- Template em templates/pos/index.html com Alpine x-data
- Hoje pos_close retorna "Erro: {e}" genérico para qualquer falha
- Não há como cancelar venda em andamento nem última venda
- services.cancellation.cancel() já existe

TAREFAS:
1. Cancelar venda em andamento:
   - Botão "Limpar" (ou tecla Esc) no template que reseta o cart Alpine
   - Puro client-side, sem POST — só limpa o x-data

2. Cancelar última venda:
   - Novo endpoint POST /gestao/pos/cancel-last/
   - Guarda order_ref da última venda no Alpine (já tem: data-order-ref no pos-result)
   - POST com order_ref → cancellation.cancel(order, reason="pos_operator", actor=f"pos:{user}")
   - Só permite se order.status in ("new", "confirmed") e created_at < 5min atrás
   - Retorna partial com feedback "Venda #XXX cancelada"

3. Erro granular no pos_close:
   - Catch ModifyService errors → "Produto X indisponível" (se stock)
   - Catch CommitService errors → "Erro ao finalizar: {detail}"
   - Catch Channel.DoesNotExist → "Canal balcão não configurado"
   - Cada erro com classe visual distinta (error-light, não genérico)

4. Template: atalho Esc=limpar, botão "Cancelar Última" aparece só se lastOrderRef existe

5. Testes: cancel-last happy path, cancel-last >5min (rejeita), cancel-last staff-only

Design tokens do storefront. Alpine para estado local, HTMX para server calls.
```

---

## P1 — CUSTOMER EXPERIENCE (backend pronto, falta UI)

### ✅ WP-R6: Alternativas Quando Esgotado

**Objetivo:** Não perder a venda quando item esgotado. Backend `find_alternatives()` pronto.

**Escopo:**
- PDP (product_detail): seção "Produtos similares" quando item indisponível ou sempre como cross-sell
- Cart: warning inline quando item no cart ficou indisponível + link para alternativas

**Done:** PDP mostra alternativas, cart avisa sobre itens indisponíveis.

**Prompt:**
```
Expor alternativas de produto no storefront do Django Shopman.

CONTEXTO:
- offering.contrib.suggestions.find_alternatives(sku, limit=4) já existe
  Retorna lista de Product com score por keywords + coleção + faixa de preço
- _helpers.py já tem _get_availability() que retorna breakdown por posição
- Templates: storefront/product_detail.html (PDP), storefront/partials/cart_item.html

TAREFAS:
1. PDP (product_detail.html):
   - Se produto indisponível: seção destacada "Veja alternativas" com grid de 2-4 produtos
   - Se disponível: seção discreta "Você também pode gostar" (colapsável)
   - Chamar find_alternatives() na view catalog.ProductDetailView, passar no contexto
   - Cada alternativa: nome, preço, badge de disponibilidade, botão quick-add

2. Cart drawer (cart_drawer.html):
   - Se item no cart está esgotado (qty > available):
     warning inline "Estoque insuficiente" + botão "Ver alternativas"
     que abre modal/drawer com find_alternatives(sku)
   - Endpoint HTMX GET /cart/alternatives/<sku>/ que retorna partial com alternativas

3. Testes: view retorna alternativas, template renderiza, endpoint HTMX funciona

Design tokens do storefront. Lazy-load alternativas no cart (HTMX on-demand).
```

---

### ✅ WP-R7: Checkout Defaults Pre-fill

**Objetivo:** Cliente que já comprou não deveria preencher tudo de novo.

**Escopo:**
- CheckoutDefaultsService.get_defaults() já retorna {fulfillment_type, payment_method, delivery_time_slot}
- Usar no GET do CheckoutView para pré-selecionar fulfillment, payment, e endereço default

**Done:** Cliente recorrente vê checkout pré-preenchido.

**Prompt:**
```
Pré-preencher o checkout com defaults do cliente no Django Shopman.

CONTEXTO:
- CheckoutDefaultsService.get_defaults(customer_ref, channel_ref) já existe e retorna dict
- O CheckoutView._checkout_page_context() já chama get_defaults e passa como ctx["checkout_defaults"]
- O template checkout.html tem x-data="checkoutPage()" com steps
- Endereços salvos já são listados e selecionáveis

TAREFAS:
1. No checkout.html, usar checkout_defaults para pré-selecionar:
   - fulfillment_type: pre-check radio "Retirada" ou "Entrega"
   - payment_method: pre-select pill
   - Se tem endereço default (saved_addresses com is_default): pre-select

2. No Alpine checkoutPage(), inicializar com valores do servidor:
   - fulfillmentType: '{{ checkout_defaults.fulfillment_type|default:"pickup" }}'
   - paymentMethod: '{{ checkout_defaults.payment_method|default:"" }}'

3. Se cliente tem endereço default → modo "confirmed" no checkoutAddress()
   com dados pré-carregados (skip search/cep)

4. Testes: cliente com defaults vê form pré-preenchido, cliente novo vê form vazio

Mínimo de mudanças. Não alterar o service — só consumir os dados que já existem.
```

---

### ✅ WP-R8: Happy Hour Badge

**Objetivo:** Cliente deve saber que está em happy hour. Hoje o desconto aplica silenciosamente.

**Escopo:**
- Banner no topo do menu quando happy hour ativo
- Badge nos produtos afetados
- Linha de desconto visível no cart

**Done:** Menu mostra happy hour ativo, cart mostra desconto.

**Prompt:**
```
Adicionar indicadores visuais de Happy Hour no storefront do Django Shopman.

CONTEXTO:
- HappyHourModifier em shopman/modifiers.py: aplica desconto se hora atual está dentro do range
- Configurável via channel.config.rules.happy_hour (start_hour, end_hour, discount_percent)
- O modifier já roda e aplica desconto, mas o cliente não vê indicação visual
- Templates: storefront/menu.html, storefront/partials/cart_drawer.html

TAREFAS:
1. Helper _is_happy_hour_active() em _helpers.py:
   - Lê config do channel web, retorna {active: bool, discount_percent: int, end_hour: int}

2. Menu (menu.html):
   - Se happy hour ativo: banner sutil no topo "Happy Hour até Xh — Y% de desconto"
   - Usar design tokens: bg-warning-light, text-warning-foreground

3. Cart drawer:
   - discount_lines do CartService já inclui happy hour se aplicado
   - Garantir que o template cart_drawer.html renderiza cada discount_line com label

4. Context processor ou view: passar happy_hour_info no contexto das pages de menu

5. Testes: helper retorna ativo/inativo, template mostra/esconde banner

Não alterar o modifier — só adicionar indicação visual.
```

---

### ✅ WP-R9: Discount Transparency no Cart

**Objetivo:** Cliente deve ver exatamente por que o preço mudou.

**Escopo:**
- Verificar se cart_drawer.html mostra discount_lines (label + valor)
- Se não mostra, adicionar
- Incluir: D-1, promoção auto, cupom, happy hour — cada um com label

**Done:** Cart mostra cada linha de desconto individualmente.

**Prompt:**
```
Garantir transparência total de descontos no cart do Django Shopman.

CONTEXTO:
- CartService.get_cart() já retorna discount_lines: lista de {label, discount_q, discount_display}
- Estas linhas vêm de session.pricing (persistido pelos modifiers)
- Templates: storefront/partials/cart_drawer.html, storefront/partials/checkout_order_summary.html

TAREFAS:
1. Ler cart_drawer.html e checkout_order_summary.html
2. Se discount_lines NÃO está sendo renderizado: adicionar seção entre subtotal e total
   - Para cada line: "{{ line.label }}: -{{ line.discount_display }}"
   - Estilo: text-success para descontos
3. Se JÁ está renderizado: verificar que cobre todos os tipos (D-1, promo, cupom, employee, happy hour)
4. Garantir que o total final é claro: Subtotal - Descontos + Taxa entrega (se WP-R1 feito) = Total

Mínimo de mudanças. Ler antes de alterar.
```

---

### ✅ WP-R10: Loyalty no Checkout

**Objetivo:** Cliente com pontos deve poder resgatar no checkout.

**Escopo:**
- Mostrar saldo de loyalty no checkout (se >0)
- Botão "Usar X pontos (= R$ Y)" que aplica como modifier
- LoyaltyRedeemModifier que subtrai do total

**Done:** Cliente com pontos pode resgatar no checkout, saldo atualizado.

**Prompt:**
```
Implementar resgate de pontos de loyalty no checkout do Django Shopman.

CONTEXTO:
- customers.contrib.loyalty: LoyaltyAccount (balance, lifetime), LoyaltyService (earn, redeem, adjust)
- LoyaltyService.redeem_points(account, points, reason) já existe
- O earn já funciona (handler dá pontos ao completar pedido)
- O checkout mostra customer_info se autenticado
- Conversion: 1 ponto = 1 centavo (ou configurável)

TAREFAS:
1. No checkout view GET: se cliente autenticado, buscar LoyaltyAccount.balance
   Passar loyalty_balance e loyalty_value_display no contexto

2. No checkout.html: se loyalty_balance > 0, mostrar seção:
   "Você tem X pontos (R$ Y). [Usar pontos]"
   Toggle Alpine que seta input hidden "use_loyalty=true"

3. No checkout POST: se use_loyalty == true:
   - Calcular pontos a usar (min(balance, order_total_q) para não ficar negativo)
   - Adicionar op set_data path="loyalty.redeem_points_q" value=X ao checkout_data

4. Modifier LoyaltyRedeemModifier (order=80):
   - Se session.data.loyalty.redeem_points_q > 0: subtrair do total
   - Adicionar discount_line com label "Resgate de pontos"

5. Post-commit handler: chamar LoyaltyService.redeem_points() com os pontos usados

6. Testes: resgate happy path, resgate > saldo (clamp), resgate 0 (no-op)

Não alterar o Core loyalty — adicionar modifier e handler no framework.
```

---

## P2 — POS PRODUCTION-READY

### ✅ WP-R11: POS Design Tokens + Layout

**Objetivo:** POS reutiliza design tokens do storefront. Layout otimizado para velocidade.

**Escopo:**
- POS herda do mesmo base CSS (design tokens, cores, radius, fonts)
- Layout 2-column: grid produtos + sidebar carrinho
- Footer com resumo de turno
- Visual clean, otimizado para toque e velocidade

**Done:** POS visualmente consistente com storefront, layout profissional.

**Prompt:**
```
Redesenhar o layout do POS usando design tokens do storefront.

CONTEXTO:
- O storefront usa design tokens CSS (--primary, --surface, --border, --foreground, etc.)
  definidos em storefront/base.html ou CSS global
- O POS em templates/pos/index.html tem CSS inline/custom
- O POS deve REUTILIZAR os mesmos tokens, não reinventar

TAREFAS:
1. POS template deve herdar de um base que inclua os design tokens
   (ou incluir o mesmo CSS do storefront)

2. Layout 2-column (como descrito na auditoria):
   - Esquerda: grid de produtos (responsivo, 3-4 cols)
   - Direita: sidebar de carrinho com items, totais, ações
   - Footer fixo: resumo de turno (vendas count + total do turno)

3. Produto tiles: usar tokens (bg-surface, border-border, text-foreground, etc.)
   - Badge D-1 (bg-warning-light) para produtos com estoque D-1
   - Badge indisponível (bg-error-light) para produtos esgotados
   - Preço em text-primary, font-bold

4. Sidebar: bg-surface, rounded-xl, shadow-sm (mesmo estilo do checkout card)

5. Botão "Fechar Venda": bg-primary text-primary-foreground, proeminente, full-width

6. Barra de busca no topo: input com tokens do storefront

7. Coleções como pills/tabs: bg-surface → bg-primary quando ativo

Manter Alpine.js para estado local, HTMX para server calls.
NÃO adicionar libs externas.
```

---

### ✅ WP-R12: POS Desconto Manual + Obs por Item

**Objetivo:** Operador precisa poder dar desconto e anotar observações.

**Escopo:**
- Modal de desconto: % ou valor fixo, motivo obrigatório
- Campo de observação por item no cart

**Done:** Operador aplica desconto com motivo, adiciona obs por item.

**Prompt:**
```
Adicionar desconto manual e observação por item no POS do Django Shopman.

CONTEXTO:
- POS em shopman/web/views/pos.py: pos_close() envia ops para ModifyService
- O ModifyService aceita op "set_data" para qualquer path em session.data
- Templates em templates/pos/index.html com Alpine x-data

TAREFAS:
1. Desconto manual:
   - Botão "% Desconto" no sidebar do POS
   - Modal Alpine com: tipo (% ou R$), valor, motivo (select: cortesia, avaria, fidelidade, outro)
   - Armazenar no Alpine state: manualDiscount = {type, value, reason}
   - No pos_close: enviar como ops set_data:
     - path="manual_discount.type" value="%"
     - path="manual_discount.value" value=10
     - path="manual_discount.reason" value="cortesia"
   - Calcular discount_q no backend (ou client-side para display + server para real)
   - Exibir no sidebar: "Desconto (cortesia): -R$ X,XX"

2. Observação por item:
   - Click no item no cart → toggle campo de texto abaixo
   - Armazenar no Alpine: item.notes = "sem açúcar"
   - No pos_close: enviar notes no add_line op ou como set_data por line_id
   - Exibir no item do cart: texto pequeno italic abaixo do nome

3. Testes: desconto %, desconto fixo, obs salva no order.data

Modal com design tokens (bg-surface, border, rounded-xl).
```

---

### ✅ WP-R13: POS Atalhos de Teclado

**Objetivo:** Velocidade. Operador não deve precisar do mouse para operações comuns.

**Escopo:**
- F1-F4: coleções, F5: limpar cart, F6: desconto, F7: obs, F8: fechar venda
- Esc: cancelar modal/desconto
- `/` ou F2: focus na busca
- Enter (no campo de busca): selecionar primeiro resultado

**Done:** Todas as operações principais acessíveis via teclado.

**Prompt:**
```
Implementar atalhos de teclado completos no POS do Django Shopman.

CONTEXTO:
- POS template em templates/pos/index.html usa Alpine x-data
- F1-F4 para coleções já existem parcialmente
- Alpine suporta @keydown.window para captura global

TAREFAS:
1. No Alpine x-data do POS, adicionar @keydown.window handler:
   - F1-F4: filtrar por coleção (índice 0-3 da lista)
   - F5: limpar cart (resetCart())
   - F6: abrir modal desconto (showDiscountModal = true)
   - F7: toggle obs no item selecionado
   - F8: fechar venda (submitSale())
   - Esc: fechar modal aberto / cancelar
   - / ou F2: focus no input de busca
   - Prevent default em todas as F-keys para não ativar browser behavior

2. Visual hint: mostrar atalhos nos botões como texto muted
   Ex: "Fechar Venda (F8)", "Limpar (F5)", "Desconto (F6)"

3. Feedback visual: flash do botão quando acionado por teclado

4. Teste manual list no prompt (não precisa de teste automatizado para keyboard)

Puro Alpine.js, sem libs externas.
```

---

### WP-R14: POS Badge D-1 + Employee Discount

**Objetivo:** Operador precisa ver D-1 e desconto staff.

**Scopo:**
- Badge D-1 nos tiles de produto (replicar lógica do storefront)
- Quando cliente é group="staff": highlight visual + desconto auto

**Done:** Tiles mostram D-1, cliente staff tem visual diferenciado.

**Prompt:**
```
Adicionar badges D-1 e employee discount visual no POS do Django Shopman.

CONTEXTO:
- No storefront, _helpers.py calcula _availability_badge() que retorna "badge-d1" para itens D-1
- No POS, _load_products() carrega produtos mas não checa disponibilidade/D-1
- EmployeeDiscountModifier aplica 20% se customer.group == "staff"
- pos_customer_lookup já retorna customer.ref e customer.group

TAREFAS:
1. D-1 Badge:
   - Em _load_products() ou endpoint separado: consultar stocking para D-1
   - Adicionar flag is_d1 no product dict
   - No tile: badge "D-1" com bg-warning-light text-warning-foreground
   - No cart: item D-1 com indicador visual e preço já com desconto 50%

2. Employee Discount:
   - Após customer lookup retornar group="staff":
     mostrar banner "Desconto funcionário 20%" no sidebar
   - Visualmente: bg-info-light border-info text na sidebar acima dos items
   - Desconto aplicado automaticamente pelo modifier (já funciona)
   - Mostrar no total: "Desc. Funcionário: -R$ X,XX"

3. Testes: D-1 flag propagado, employee highlight aparece

Design tokens do storefront para badges.
```

---

### WP-R15: POS Resumo de Turno

**Objetivo:** Operador precisa saber quantas vendas fez e total.

**Escopo:**
- Footer fixo com: N vendas, total R$ X
- Dados calculados do banco (orders com channel=balcao, actor=pos:user, today)

**Done:** Footer mostra vendas do turno em tempo real.

**Prompt:**
```
Adicionar resumo de turno no POS do Django Shopman.

CONTEXTO:
- POS cria orders com channel "balcao" e ctx actor "pos:{username}"
- Template pos/index.html

TAREFAS:
1. Novo endpoint GET /gestao/pos/shift-summary/ (HTMX partial):
   - Query: Order.objects.filter(channel__ref="balcao", created_at__date=today)
     .exclude(status="cancelled")
   - Retornar: count, total_q (sum), total_display

2. Template partial pos/partials/shift_summary.html:
   - "Turno: {count} vendas — R$ {total_display}"
   - Refresh automático via hx-trigger="posOrderCreated from:body, every 60s"

3. Footer fixo no pos/index.html:
   - Include do partial
   - Estilo: bg-surface border-t, text-sm, flex justify-between
   - Esquerda: turno summary
   - Direita: último pedido ref + total

4. Após pos_close sucesso: trigger HX-Trigger="posOrderCreated" para refresh do footer

5. Testes: summary com 0 vendas, summary com N vendas, cancellation não conta

Sem estado Alpine para isso — server-side via HTMX.
```

---

### WP-R16: POS Gestão de Caixa

**Objetivo:** Abertura, sangria, e fechamento de caixa.

**Escopo:**
- Modelo CashRegisterSession (opened_at, closed_at, opening_amount_q, closing_amount_q, operator)
- CashMovement (type: in/out/adjustment, amount_q, reason, timestamp)
- UI: botão "Abrir Caixa" (se fechado), "Sangria" (modal), "Fechar Caixa" (relatório)
- Bloqueio: POS não permite venda sem caixa aberto

**Done:** Operador abre/fecha caixa, registra sangrias, relatório de fechamento.

**Prompt:**
```
Implementar gestão de caixa no POS do Django Shopman.

CONTEXTO:
- O modelo DayClosing já existe em shopman/models/ mas é simplificado (relatório diário)
- Precisamos de gestão de caixa real: abertura, sangria, fechamento por turno/operador

TAREFAS:
1. Modelos em shopman/models/cash_register.py:
   - CashRegisterSession: operator (FK User), opened_at, closed_at,
     opening_amount_q, closing_amount_q, expected_amount_q (calculado),
     difference_q, notes, status (open/closed)
   - CashMovement: session (FK), type (sangria/suprimento/ajuste),
     amount_q, reason, created_by, created_at

2. Views em shopman/web/views/pos.py (ou novo arquivo pos_cash.py):
   - GET /gestao/pos/caixa/ — status atual (aberto/fechado)
   - POST /gestao/pos/caixa/abrir/ — criar CashRegisterSession com opening_amount_q
   - POST /gestao/pos/caixa/sangria/ — registrar CashMovement
   - POST /gestao/pos/caixa/fechar/ — calcular expected, registrar closing, mostrar relatório

3. Bloqueio: se não há CashRegisterSession aberta para o user, POS mostra tela "Abrir Caixa"
   em vez do grid de produtos. Apenas staff pode abrir.

4. Relatório de fechamento:
   - Vendas em dinheiro: sum orders payment=dinheiro
   - Sangrias: sum CashMovement type=sangria
   - Suprimentos: sum type=suprimento
   - Expected = opening + vendas_dinheiro + suprimentos - sangrias
   - Diferença = closing - expected

5. Admin: CashRegisterSession + CashMovement inline

6. Testes: abrir, sangria, fechar com cálculos corretos

Migrations necessárias. Design tokens do storefront.
```

---

## P3 — ROBUSTEZ

### WP-R17: Service Failure Handling

**Objetivo:** Gateway down não pode travar o sistema.

**Scopo:**
- Payment gateway timeout → order fica pendente com mensagem clara
- Stock service down → checkout mostra "verificação de estoque temporariamente indisponível"
- Notification failure → log + retry (não bloqueia flow)

**Done:** Falhas externas degradam graciosamente com mensagens claras.

**Prompt:**
```
Implementar graceful degradation para falhas de serviços externos no Django Shopman.

CONTEXTO:
- shopman/services/payment.py: initiate() chama adapter que chama API externa (Stripe, EFI)
- shopman/services/stock.py: hold() chama stocking backend
- shopman/services/notification.py: send() chama ManyChat/email
- Hoje, exceções em adapters propagam para views com except Exception genérico

TAREFAS:
1. Payment initiate failure:
   - Se adapter.create_intent() falha (timeout, 5xx):
     order criada mas sem intent, payment.status = "pending_retry"
   - Checkout redireciona para tracking com mensagem "Pagamento será processado em breve"
   - Directive enfileirada para retry do initiate (com backoff)

2. Stock check failure (checkout):
   - Se _get_availability() falha:
     log warning, continuar checkout sem block (melhor vender que perder venda)
   - Adicionar flag "stock_check_unavailable" em order.data para review posterior

3. Notification failure:
   - Já é fire-and-forget via directives, mas verificar que falha não bloqueia flow
   - Adicionar retry count em directive payload (max 3)

4. Testes: mock adapter timeout → verificar graceful degradation em cada cenário

Não alterar o Core. Wrapping no framework service layer.
```

---

### WP-R18: Concurrent Checkout Stress Test

**Objetivo:** Garantir que 2+ checkouts simultâneos do mesmo item não causam oversell.

**Done:** Teste com N threads fazendo checkout, verifica que holds + stock estão consistentes.

**Prompt:**
```
Criar teste de stress de checkout concorrente no Django Shopman.

CONTEXTO:
- CommitService usa select_for_update() na session
- Stock holds usam Move com transaction.atomic()
- Payman usa select_for_update() no intent

TAREFAS:
1. Test com ThreadPoolExecutor (5 threads):
   - Criar produto com stock = 3
   - 5 sessions, cada uma com qty=1
   - 5 commits simultâneos
   - Verificar: exatamente 3 orders criadas, 2 falham com stock error
   - Verificar: stock holds = 3, não mais

2. Test de double-submit:
   - Mesmo session_key + mesmo idempotency_key
   - 2 commits simultâneos
   - Verificar: exatamente 1 order criada (idempotency key funciona)

3. Test de payment race:
   - 2 threads tentam capture no mesmo intent
   - Verificar: 1 sucesso, 1 falha

Usar TransactionTestCase (requer DB real para locks).
Pode precisar de @pytest.mark.django_db(transaction=True).
```

---

### WP-R19: Error Paths nos Views

**Objetivo:** Views devem tratar cenários de erro com mensagens claras.

**Done:** Edge cases testados e tratados com UX adequada.

**Prompt:**
```
Tratar error paths nos views do storefront do Django Shopman.

CONTEXTO:
- 42 except Exception silenciosos mapeados na auditoria anterior
- Cenários: cart inválido no checkout, session expirada, item repriced, payment method indisponível

TAREFAS:
1. Cart inválido no checkout (session not found ou state != "open"):
   - Detectar no CheckoutView.post()
   - Redirecionar para /cart/ com message "Seu carrinho expirou. Adicione os itens novamente."

2. Session expirada (TTL 30min):
   - CartService.get_cart() retorna cart vazio se session expirada
   - Adicionar flash message quando session existed but expired

3. Item repriced entre add-to-cart e checkout:
   - No checkout validation: comparar unit_price_q no session com preço atual do produto
   - Se diverge >5%: warning "O preço de X mudou para R$ Y. Deseja continuar?"
   - Não bloquear — informar

4. Payment method indisponível:
   - Se canal removeu "pix" entre cart e checkout:
     erro claro "Método de pagamento indisponível. Selecione outro."

5. Substituir os 5 piores except Exception (em checkout.py e cart.py) por except específicos
   com logging adequado

6. Testes para cada cenário

Não substituir todos os 42 de uma vez — focar nos hot paths (checkout, cart, payment).
```

---

### WP-R20: Migration Audit + Missing Migrations

**Objetivo:** Garantir que o schema está correto após reestruturações.

**Done:** `makemigrations --check` passa, todas as migrations aplicadas.

**Prompt:**
```
Auditar e corrigir migrations do Django Shopman.

CONTEXTO:
- A migration 0005_google_maps_address.py foi deletada durante WP-R9 (restructure)
- Os campos existem nos modelos mas a migration pode estar faltando
- Reestruturações podem ter deixado migrations órfãs ou faltantes

TAREFAS:
1. Rodar python manage.py makemigrations --check --dry-run
   - Se detectar mudanças pendentes: criar migrations

2. Verificar que todos os campos de Shop (google places fields) estão cobertos por migrations

3. Verificar que modelos novos (se WP-R1 DeliveryZone, WP-R16 CashRegister) têm migrations

4. Rodar python manage.py migrate --run-syncdb (se necessário)

5. Verificar consistência: python manage.py showmigrations | grep "\[ \]"

Não squashar migrations existentes. Apenas criar faltantes.
```

---

## Ordem de Execução Recomendada

```
Sprint 1 (P0 bloqueantes):
  WP-R1 (delivery zone/fee) → WP-R2 (Stripe) → WP-R3 (webhook tests)
  WP-R4 (counter payment) → WP-R5 (POS cancel)

Sprint 2 (P1 customer experience):
  WP-R6 (alternativas) → WP-R7 (checkout defaults) → WP-R8 (happy hour)
  WP-R9 (discount transparency) → WP-R10 (loyalty checkout)

Sprint 3 (P2 POS):
  WP-R11 (POS layout/tokens) → WP-R12 (desconto/obs) → WP-R13 (atalhos)
  WP-R14 (D-1/employee) → WP-R15 (turno) → WP-R16 (caixa)

Sprint 4 (P3 robustez):
  WP-R17 (failure handling) → WP-R18 (concurrent test) → WP-R19 (error paths)
  WP-R20 (migration audit)
```

**Dependências:**
- WP-R12 (desconto POS) depende de WP-R11 (layout POS)
- WP-R10 (loyalty) é independente — pode ser feito a qualquer momento
- WP-R20 (migrations) deve ser rodado após qualquer WP que crie modelos
