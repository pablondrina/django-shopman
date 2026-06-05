# Spec — Storefront (Loja Online) [Etapa C]

> Iniciativa [[project_excellence_refactor_initiative]]. Pilar **Loja Online**. Ancorada na
> arquitetura de 3 camadas, no contrato projection+comando, nos tenets do [Confronto](02-confronto.md)
> e no [Mapa do Core](00-core-capability-map.md). É o "nosso próprio Shopify" voltado ao cliente:
> **fluidez Shopify com alma omotenashi, BR-first.** Define *o quê* e *o contrato*; a UI visual/pixel
> é refinamento posterior.

## 0. Posição na arquitetura (inegociável)
- O Storefront é uma **superfície = apresentação pura**. Consome **read-models de DADO** +
  `SurfaceActionProjection` do orquestrador; renderiza. **Zero política, zero Core, zero
  aritmética/HTML em view ou template.** Toda decisão (preço, disponibilidade, elegibilidade,
  transição) vem do orquestrador.
- **Stack:** Django + **HTMX (servidor) ↔ Alpine (DOM)**, Tailwind com design tokens do `Shop`
  (sem lib de componentes externa — convenção [[feedback_no_external_component_lib]]). (As superfícies
  Nuxc/UI-Thing são PDV/agentic/backstage; o storefront cliente segue HTMX/Alpine.)
- **Camada de apresentação explícita** (`storefront/projections/`): pega o read-model de dado do
  orquestrador e dá o **shape de tela** (copy, formatação, layout). Mata o `cart.py::get_cart`/
  `product_cards` (que faziam política). **Um shape de card só.**
- **Config-driven:** comportamento por `ChannelConfig` (canal `online`/web), copy por
  `OmotenashiCopy`, branding por `Shop` (OKLCH/fontes/logo), notificações por `NotificationTemplate`.
  **Nada de vertical food/BR hardcoded.**

## 1. Tenets do Storefront (regem cada tela)
1. **Omotenashi + acessibilidade são first-class** ([[feedback_accessibility_omotenashi_first_class]]):
   copy acolhedor (via OmotenashiCopy), heading grande, contraste alto, idosos em mente, foco/ARIA,
   teclado. Não é polish — é requisito de cada tela.
2. **Fluidez:** one-page onde der, reveal progressivo, **total/disponibilidade recalculam ao vivo**
   (HTMX + SSE push `stock-{ref}`), low-friction (sem-login até onde possível).
3. **Availability-first, acionável:** disponibilidade nunca é só informativa — é **1-clique**
   ([[project_stock_ux_spec]]); planned-hold com UX explícita ("Aguardando confirmação" / "Tudo
   pronto! Confirme") + countdown + polling/SSE.
4. **Timeouts transparentes** ([[feedback_transparent_timeouts]]): todo TTL que afeta o cliente tem
   UI explícita + notificação ativa pelo canal certo.
5. **Maps-first endereço** ([[project_address_ux_spec]]): Google Places + **"usar localização atual"**
   (iFood); CEP só fallback. (NÃO o CEP-first do Shopify.)
6. **PIX-first pagamento** (BR), via adapters; métodos por `ChannelConfig.payment`.
7. **SEO é capítulo próprio** ([[project_seo_chapter]]): keywords (taggit) alimentam busca +
   alternatives + meta tags + schema.org. Server-rendered (HTMX) ajuda.
8. **PWA** (add-to-home, ícones) — app-like, instalável.

## 2. Telas e o contrato que cada uma consome

### 2.1 Home / Catálogo (descoberta)
- **Read-model:** catálogo do canal (`CatalogService.get_sellable_products(ref)` →
  read-model de dado do orquestrador: itens com preço-em-contexto + disponibilidade-em-contexto +
  coleção primária + keywords). **A apresentação** monta: hero (branding Shop), **rail/círculos de
  categoria** (stories, do Take.app), grade de cards.
- **Card de produto (UM shape só):** imagem-forward, preço (com riscado se promo), badge de
  disponibilidade **acionável** (Availability enum + label PT), CTA add-to-cart. Sem 2º shape/2º
  template (mata `availability_preview.html`).
- **Conversão (benchmark):** fresh-from-oven / "saiu do forno" (via dado do orquestrador, não
  string-match hardcoded — externalizar), happy-hour badge (config), **"Siga"** (re-engajamento).
- **SEO:** server-render, meta/schema por produto/coleção.
- **Busca:** `CatalogService.search` (keywords/coleção/nome). Resultado = mesmo card.

### 2.2 PDP (página de produto)
- **Read-model:** produto + preço-em-contexto + disponibilidade-em-contexto + nutrição
  (`nutrition_facts`) + ingredientes + peso (`unit_weight_g`) + galeria.
- **Apresentação:** título grande, preço próximo ao **peso/nutricional/ingredientes**
  ([[project_pdp_data_fields_pending]]), stepper, **"Adicionar R$X"** (cor da marca).
- **Indisponível:** CTA "Me avise" ([[project_notify_me_pending]] — feature futura) +
  **substitutos** (`find_substitutes`, "Outras opções" — substituição, modal/indisponível).
- **Cross-sell:** seção **"Talvez você também goste"** ([[project_pdp_veja_tambem_pending]] — copy
  decidida; descoberta lateral, sempre visível, ≠ substituição).
- **Planned-hold:** se `availability_policy=demand_ok`/planned, mostrar "encomenda" com a UX de
  confirmação otimista.

### 2.3 Carrinho
- **Read-model:** `cart_context` (read-model de DADO: linhas com preço-em-contexto, disponibilidade
  por linha, descontos aplicados, totais, fee de entrega) + `SurfaceActionProjection` (pode_checkout,
  ações por linha). **NÃO** o `CartService.get_cart` atual.
- **Apresentação:** **cart drawer** (overlay, mantém contexto) + **sticky cart bar mobile** (Take.app)
  + steppers + **nudge de frete grátis com progress bar** + order summary com total sempre visível +
  badge planned-hold por linha (countdown).
- **Live:** mudanças recalculam via HTMX; SSE `stock-{ref}` atualiza disponibilidade sem polling.

### 2.4 Checkout (one-page, o coração da fluidez)
- **Read-model:** `checkout_context` (dado: fulfillment options, endereços salvos, slots de retirada,
  métodos de pagamento do canal, totais com frete) + `SurfaceActionProjection`.
- **Fluxo one-page, reveal progressivo** (Shopify v11): Fulfillment (entrega/retirada) → Contato →
  **Endereço Maps-first** (se entrega; autocomplete + localização atual + pin móvel) → Slot →
  Pagamento (**PIX-first**) → Revisar → Confirmar. **Total/frete recalculam ao vivo** ao completar
  endereço (a alavanca de disponibilidade/pricing do Core decide).
- **Low-friction:** sem-login (OTP/AccessLink quando necessário, `PRESERVE_SESSION_KEYS` carrega o
  carrinho no login); reconhecer endereço/último/padrão **pra confirmar, não perguntar**.
- **Comando:** `checkout.process` (via `sessions.commit_session`) — idempotente. O Storefront só
  emite o comando; o orquestrador faz o saga (hold/payment/KDS/notify) por `ChannelConfig`.
- **Confirmação otimista:** pós-commit, `ChannelConfig.confirmation` rege (auto-confirm/timeout);
  a tela mostra o estado real e o timeout transparente.
- **Order-as-message (ponte agentic R1):** opção "finalizar/continuar no WhatsApp" via `AccessLink`
  (sem-login) — D4. Copy via OmotenashiCopy.

### 2.5 Acompanhamento (order tracking)
- **Read-model:** `order_tracking` (dado: status, timeline events, ETA timestamp, fulfillment,
  pagamento). **A apresentação** formata copy/ETA/progress steps (HOJE isso está no orquestrador —
  1.652 linhas — e deve **migrar pra cá** no split). Copy via OmotenashiCopy.
- **Live:** SSE/polling; timeouts/transições transparentes; ações pós-pedido (cancelar dentro da
  janela otimista) via SurfaceAction.

### 2.6 Conta / Auth
- **Read-model:** cliente (Guestman: perfil, endereços, histórico via `CustomerOrderHistoryService`,
  loyalty/insights se aplicável). **Auth:** doorman OTP / magic link / device trust.
- **Reorder** ([[project]] reorder): 1-clique a partir do histórico.
- Low-friction: OTP por WhatsApp (ManyChat) / email; device trust pra pular OTP.

## 3. Cross-cutting (config-driven, não hardcoded)
- **Copy:** TUDO acolhedor via `OmotenashiCopy` (key/moment/audience). Zero string PT-BR de UX no
  código de superfície ou orquestrador.
- **Branding:** `Shop` design tokens (cor âmbar Nelson OKLCH, fontes, logo, radius) → Tailwind tokens.
- **Comportamento:** `ChannelConfig` do canal web (confirmation, payment, stock scope, etc.).
- **Notificações:** `NotificationTemplate` por evento; cadeia phone-first (ManyChat→sms→email);
  filtro de consentimento (LGPD, Guestman consent).
- **Vertical (fresh-from-oven, happy-hour, D-1):** vira dado/config (rule types + RuleConfig),
  consumido como flag — não string-match no storefront.

## 4. O que o Storefront NÃO faz (anti-frankenstein)
- Não calcula preço/desconto/disponibilidade (consome do orquestrador).
- Não importa models do Core nem chama métodos privados (mata `product_cards._best_auto_promotion…`).
- Não monta HTML em view (CEP lookup/toasts → projection/service + fragmentos de template).
- Não tem 2 shapes de card / 2 templates pro mesmo conceito.
- Não decide lifecycle/transição (emite comando; orquestrador decide).

## 5. Conserto concreto (do audit → para a superfície limpa)
1. **Aposentar `storefront/cart.py::CartService.get_cart()`** → `cart_context` (read-model de dado) +
   `storefront/projections/cart` (apresentação). `CartService` vira adapter session-key↔Orderman.
2. **Matar `storefront/services/product_cards.py`** (promo via métodos privados) → caminho canônico
   `contextual_price`; um card via `build_catalog_items_for_skus`; deletar `availability_preview.html`.
3. **Migrar a apresentação do `order_tracking`** (copy/ETA/steps) do orquestrador → `storefront/
   projections/order_tracking` (o dado fica no orquestrador). [parte do split do read-side]
4. **CEP/toasts/HTML** fora das views → projection/service (geocoding já existe) + fragmentos.
5. Consolidar as 3 cópias de `availability_for_skus` no read-model de dado.

## 6. Alavancas do Core que o Storefront consome (referência)
- Catálogo/preço: `CatalogService.get_price/get_sellable_products/search/find_substitutes`,
  `contextual_price` (read-model de dado).
- Disponibilidade: `availability_for_skus`, planned holds, SSE `stock-{ref}`.
- Pedido: `sessions.create/modify/commit`, `checkout.process`; `order_tracking` (dado).
- Cliente/auth: Guestman (lookup/history/address/insights), doorman (OTP/AccessLink/device).
- Pagamento: payman + adapters (PIX-first).
- Config/copy: `ChannelConfig`, `OmotenashiCopy`, `NotificationTemplate`, `Shop` branding.

## 7. Aberto (decidir na implementação / com Pablo)
- Express/PIX-1-toque no checkout (avaliar — Shopify express). 
- "Me avise" (notify-me) — feature futura, gancho na PDP.
- Scroll inteligente ([[project_scroll_inteligente_pending]]) + bug de scroll
  ([[project_scroll_misbehavior_pending]]) + badge cart mobile ([[project_bottom_nav_cart_badge_pending]]).
- Forma exata do read-model-de-DADO vs projeção-de-apresentação (contrato preciso) — sai em D.
</content>
