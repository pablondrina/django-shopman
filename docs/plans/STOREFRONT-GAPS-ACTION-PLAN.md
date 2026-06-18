# STOREFRONT-GAPS — plano de ação (pós revisão reversa)

> **Origem.** Saiu da revisão às avessas em [`docs/reference/storefront-spec.md`](../reference/storefront-spec.md)
> (seção 6, Gaps). Cada WP é auto-contido: problema → contexto recuperado → abordagem proposta
> (simples · robusta · elegante) → decisões abertas p/ o Pablo → esforço/risco. Princípios do projeto
> valem (omotenashi first-class, zero gambiarra, respeitar o Core, confirmar UX cedo/inline).
>
> Depois de atacar (ou priorizar) estes, **retomamos a Revisão Reversa Spec-driven** para as outras
> superfícies (PDV, backstage/KDS) e/ou re-spec do storefront pós-correções.

## Status da camada visual Nuxt (fase A) — ✅ CONCLUÍDA (2026-06-17)

Os backends WP-1..WP-6 já estavam feitos; a **camada visual Nuxt foi entregue e
verificada ao vivo** (preview 127.0.0.1:3000), commit por WP, `make test` 1828 +
`make lint` + vitest 217 verdes:

- **WP-1** (`288fd141`): toggle "Salvar para a próxima vez" no checkout (pré-marcado,
  opt-out) → `save_as_default=false` quando desmarcado.
- **WP-2/WP-3** (`e5e665e4`): badge "Pausado" (is_paused) nos cards/PDP; CTA reusável
  `StockNotifyButton` (logado 1-clique / anônimo popover de telefone) quando
  is_notifiable. **+ correção de presentation**: is_paused agora honra produto
  publicado-mas-não-vendável (catalog.py/product_detail.py).
- **WP-4** (`208fb628`): coração `FavoriteHeart` + `useFavoritesState` (otimista,
  sincroniza instâncias, version pós-confirmação); prateleira `MenuFavoritesShelf`
  "Seus favoritos"; seed += new_arrivals → 4 coleções (Destaques/Direto do forno/
  Novidades/Seus favoritos). "Direto do forno" (fresh_from_oven) só aparece com
  dados de produção.
- **WP-5** (`d524b552`): `DietaryWarningBadges` (âmbar, ícone, omotenashi) em
  card+PDP; filtro "Só compatível com minhas preferências" no menu (off, contador
  "N ocultos", pills de seções vazias somem).
- **WP-6**: cross_sell já renderiza na PDP ("Você também pode gostar") — confirmado.
  *(Nota: o plano citava "Talvez você também goste"; a loja usa "Você também pode
  gostar" — ambas válidas, deixado como está.)*

**Falta (fase B+):** WP-7 (dietético/nutricional via Recipe/BOM), WP-8 (gate
browser-QA Omotenashi no CI), WP-9 (e2e/locust), WP-11 (entrega — decisões com Pablo),
WP-10 resto.

---

## Princípio transversal: Omotenashi é passageiro de 1ª classe

O headless **removeu do CI o gate de browser-QA Omotenashi** (ele navegava as páginas Django, mortas).
Não pode ficar sem. **WP-8 reconstrói esse gate contra a loja Nuxt** — é pré-requisito de "pronto",
não follow-up opcional. Toda feature abaixo nasce com copy via `OmotenashiCopy`/catálogo e estados
acolhedores (informar, nunca bloquear seco).

---

## Tier 1 — impacto direto no cliente

### WP-1 — Checkout volta a persistir endereço/cliente/defaults  ✅ FEITO (commit `6f5a6bfa`) · ⏱ pequeno · risco baixo
> Efeitos pós-commit (`ensure_customer`/`persist_new_address`/`save_defaults`) movidos p/ dentro de
> `checkout.process()` (fonte única; só o storefront chama process(), POS tem caminho próprio),
> best-effort. `save_as_default` default True (omotenashi); toggle Nuxt "Salvar p/ a próxima vez"
> (pré-marcado, opt-out) = peça de front pendente. Testes `test_checkout_side_effects.py` verdes.
**Problema (brecha REAL confirmada).** A view de página Django (apagada) chamava, pós-commit:
`checkout_service.ensure_customer()`, `persist_new_address()`, `save_defaults(enabled=...)`. A
`CheckoutView` da API (`shopman/storefront/api/views.py`) só faz `process()` + `grant_order_access` +
limpa carrinho. Hoje a loja Nuxt **não salva endereço novo na conta, não faz upsert do cliente, nem
salva defaults**. Os 3 serviços existem (`shopman/shop/services/checkout.py`), só não são chamados.
**Confirmado:** `grep ensure_customer|persist_new_address|save_defaults shopman/storefront/api/` → vazio.

**Abordagem.** Mover os 3 efeitos pós-commit para **dentro de `checkout_service.process()`** (fonte
única — toda superfície ganha), tornando-os idempotentes e à prova de exceção (não derrubar o checkout
se a persistência falhar — eles já são "best effort"). Verificar que o PDV (`shop/services/pos.py`, que tem `_ensure_customer_*` próprios) não duplica.
**DECIDIDO (omotenashi):** o **endereço novo salva sempre** (é do próprio cliente). As escolhas
(fulfillment/pagamento/horário) viram o pré-preenchido da próxima vez. Existe um toggle **visível e
já marcado** ("Salvar para a próxima vez") que o cliente pode desmarcar — default na hospitalidade,
controle preservado. `save_defaults` roda salvo se o toggle for desmarcado.
**Cobertura:** `test_persist_address.py` já existe (serviço); adicionar teste do caminho API.

### WP-2 — Revisão do vocabulário de disponibilidade  ✅ FEITO (commit `feat WP-2`) · ⏱ médio · risco baixo
> `is_paused` + `is_notifiable` expostos nas projeções de catálogo e PDP (`is_notifiable` = esgotado
> honesto: UNAVAILABLE + vendável + não pausado → habilita "Me avise"). Testes verdes.
> **Follow-up:** "Volta em {data}" p/ PLANNED_OK precisa de plumbing do `target_date` no `raw_avail`
> (não está lá hoje) — fica p/ depois; PLANNED_OK já é vendável, então não urge.
**Problema.** O enum tem 4 estados (`AVAILABLE/LOW_STOCK/PLANNED_OK/UNAVAILABLE`). O motor por baixo
(AVAILABILITY-PLAN, scope unification, planned holds) é robusto, mas a **superfície colapsa**
"pausado" e "esgotado sem plano" ambos em `UNAVAILABLE` — distinção que importa para a UX (e habilita
WP-3 e WP-5).
**Contexto recuperado.** `availability.check()` já carrega `is_paused`, `planned_target_date`,
`is_tracked` (ver `project_stockman_scope_unified`, `project_availability_plan_status`). O dado existe;
falta **surfaceá-lo**.
**Abordagem.** Não inflar o enum à toa. Manter os 4 estados + expor flags semânticas já existentes
(`is_paused`, `planned_target_date`) na projeção de disponibilidade do storefront, e mapear UX:
- `PLANNED_OK` → "Volta em {data}" / vendável (pré-encomenda).
- `UNAVAILABLE` + `is_paused` → "Pausado" (decisão do operador).
- `UNAVAILABLE` sem plano → estado honesto → **CTA "Me avise" (WP-3)**.
**Entrega:** documentar o modelo completo na spec (a parte robusta hoje é invisível) + ajustar copy.

### WP-3 — "Me avise quando disponível"  ✅ BACKEND FEITO (commit feat WP-3) · 🥇 ouro
> Modelo StockAlertSubscription (+migração), serviço subscribe/notify idempotente, endpoint
> `POST /api/v1/availability/<sku>/notify/` (anônimo só-telefone OU logado), trigger no Move
> (apps.ready → on_commit) só quando há pendente. Falta CTA na PDP Nuxt (lê `is_notifiable`).
**Contexto recuperado (`project_notify_me_pending`).** Desenho já decidido (2026-04-18):
- Modelo `StockAlertSubscription(sku, channel, contact/customer, subscribed_at, notified_at)`.
- Disparo: signal de Stockman `Move` quando `ready` passa de 0 → positivo (reusar o caminho de
  `on_holds_materialized`/`stock.arrived` que já existe — WP-AV-12).
- UI: CTA na PDP **só** no estado `UNAVAILABLE` sem plano (WP-2 garante que esse estado é honesto).
- Notificação respeita prefs do Guestman (ManyChat→WhatsApp; email pro resto) — reusa
  `shop/services/notification.py` + magic link da loja.
**Abordagem.** Slice fino: modelo + subscribe endpoint (`POST /api/v1/availability/<sku>/notify/`) +
template de notificação `stock_back`. CTA na PDP Nuxt (lê `is_notifiable` do WP-2).
**Trigger VALIDADO (sem detecção frágil de borda 0→+):** num receiver de mudança de estoque (Move
post_save, mesmo ponto do `_sse_emitters`), se houver assinatura **pendente** (`notified_at IS NULL`)
p/ o SKU **E** `availability.check` agora diz disponível → notifica + marca `notified_at`. Idempotente,
dispara uma vez. Fast-path: só consulta se `exists()` de assinatura pendente p/ aquele SKU.
**Onde mora o modelo:** `storefront/models/` (app-level, como Promotion/Coupon/DeliveryZone) — precisa
migração.
**DECIDIDO:** anônimo **pode** se inscrever (só telefone/WhatsApp) — reduz fricção; valida via o
mesmo OTP se virar pedido.

### WP-4 — Favoritos  ✅ BACKEND FEITO (commit feat WP-4) · ⏱ médio-grande
> Modelo CustomerFavorite (+migração), serviço add/remove/toggle/skus, endpoints
> `GET/POST/DELETE /api/v1/account/favorites/[<sku>/]`, flag `is_favorite` nas projeções.
> Coleções globais (featured/fresh_from_oven/new_arrivals) já existem. Falta coração na UI Nuxt
> + expor as 4 coleções na home/menu.
**Contexto recuperado.** `shopman/shop/dynamic_collections.py` é um **registry vivo** com resolvers
`featured` (mais vendidos 30d), `fresh_from_oven`, `new_arrivals`, configurável por canal em
`Shop.defaults["menu"]["dynamic_collections"]`. **Favoritos = uma coleção dinâmica client-scoped.**
**DECIDIDO — conjunto canônico (4):** **Destaques** (=`featured`), **Direto do forno**
(=`fresh_from_oven`), **Novidades** (=`new_arrivals`), **Seus favoritos** (novo, **explícito**).
*(Sem "Você já pediu" implícito por ora — favoritos é só o explícito.)*
**Abordagem.** Favoritos = `CustomerFavorite(customer, sku)` + botão coração (PDP/card), toggle
otimista, `POST/DELETE /api/v1/account/favorites/<sku>/`, exposto como resolver dynamic `favorites`
(client-scoped). Login obrigatório (é por cliente); coração em estado anônimo convida a logar
(omotenashi). Labels via `OmotenashiCopy`.
**Pré-checagem:** confirmar que home/menu Nuxt **renderizam** as dynamic collections hoje (a
presentation resolve, mas a loja pode não exibir todas) — parte do trabalho é expor as 4.

### WP-5 — Preferências alimentares  ✅ AVISO FEITO (commit feat WP-5) · ⏱ médio
> `dietary_warnings` nas projeções de catálogo+PDP (conservador: só conflito claro). Mapeamento
> tunável em `presentation/dietary.py`. Falta: badge no card/PDP Nuxt + o FILTRO opcional no menu
> ("Só compatível com minhas preferências").
**Problema.** Prefs alimentares são salvas (toggles em `/account/preferencias`), mas **não fazem nada**
no catálogo.
**Contexto.** Produtos já têm dieta/alergênicos (`product_detail.py`: allergens, dietary). Prefs do
cliente em `customer_context`/Guestman.
**Abordagem (omotenashi: informar > bloquear).** Camada "preference-aware" em TODA superfície de
produto:
- **Aviso inline** no card e na PDP quando o produto conflita com uma pref ativa (ex.: cliente
  marcou "sem glúten" → badge discreto "Contém glúten" no card; alerta claro na PDP). Nunca esconder
  sem avisar.
- **Filtro opcional** no menu/busca: toggle "Só compatível com minhas preferências" (off por padrão;
  esconde com contador "N itens ocultos pelas suas preferências" — transparente, reversível).
**DECIDIDO:** o atributo dietético **deriva da Recipe/BOM** (junto com WP-7), não duplicado no
`Product`. **Aberto (menor):** o conjunto exato de prefs (vegano, sem glúten, sem lactose, …) e o
mapeamento pref→atributo — definir ao executar.

---

## Tier 2 — descoberta / PDP (specs prontas, só executar)

### WP-6 — "Talvez você também goste" na PDP  ✅ JÁ EXISTIA (backend)
> `cross_sell` na projeção PDP via `related_skus` (scorer por keywords), copy correta. Só falta
> confirmar o render no Nuxt (já existe per o mapa).
`project_pdp_veja_tambem_pending`: descoberta lateral (NÃO substituição). Reusar o scorer de
`find_substitutes(require_available=False, exclude_self=True)`. Copy fixa: **"Talvez você também
goste"**. Grid após a descrição. Zero acoplamento com disponibilidade.

### WP-7 — Dados da PDP via Recipe/BOM  ✅ CONCLUÍDO (2026-06-17) · ESCOPO REAL apurado (investigação do Core)

> **FEITO.** Alérgenos/dieta agora derivam da Recipe/BOM, espelhando o padrão da nutrição.
> `make test` 1844 + `make lint` + gate Admin/Unfold verdes; verificado ao vivo na PDP (Nuxt).
> Entregue:
> - `packages/craftsman/shopman/craftsman/dietary.py` — dataclass `IngredientDietary`
>   (schema dietético de `RecipeItem.meta`: `allergens` + `diet` ∈ {vegan, vegetarian, animal}).
> - `shopman/shop/services/recipe_bom.py` — `expand_recipe_items` extraído (DRY: nutrição + dieta
>   compartilham a expansão recursiva do BOM com cycle-detection).
> - `shopman/shop/services/dietary_from_recipe.py` — `aggregate_dietary_from_recipe(product)`:
>   união de alérgenos; "100% vegetal" se TODOS vegan, "vegetariano" se NENHUM animal; "sem glúten"/
>   "sem lactose" se NENHUM insumo dispara; grava `Product.metadata` com sentinel
>   `dietary_auto_filled` (respeita override manual). **Segurança:** só materializa se TODOS os
>   insumos declararem perfil (rotulagem de alérgeno incompleta é perigosa → no-op).
> - Signal `post_save` em Recipe unificado (`_connect_recipe_derivation_signal`): nutrição + dieta.
> - Form admin Craftsman (`RecipeItemInlineForm`): campos `diet` + `allergens_text` por insumo.
> - Form admin Offerman (`ProductAdminForm`): sentinel `dietary_auto_filled` preservado; só vira
>   manual quando o operador realmente muda a dieta (sem footgun ao re-salvar).
> - Seed: `INGREDIENT_PROFILES` ganhou `allergens` + `diet` por insumo; chama a agregação.
> - Testes: `shopman/shop/tests/test_dietary_from_recipe.py` (16) + atualizações em
>   test_admin_nutrition + test_admin_operational_integration.
> **Achado:** a derivação corrige divergências do stopgap manual — ex.: CHALLAH (massa com leite+
> manteiga) agora declara honestamente `leite`/lactose, onde o seed manual dizia "sem lactose".

**ORIGINAL (referência do escopo):**

**O Core já resolve a maior parte.** Mapa (file:line) levantado por investigação completa:
- ✅ **Peso junto ao preço** — JÁ FEITO. `Product.unit_weight_g` → `unit_weight_label` exibido nos
  cards (ProductTile/ProductListItem) e na PDP, junto ao preço. Nada a fazer.
- ✅ **Nutricional somado** — JÁ DERIVA da Recipe/BOM. `shop/services/nutrition_from_recipe.py`
  (`fill_nutrition_from_recipe`, signal `post_save` em Recipe) expande BOM recursivamente, soma
  `RecipeItem.meta["nutrition"]` (por 100g), escala p/ serving, materializa `Product.nutrition_facts`
  (flag `auto_filled`, respeita override manual). PDP lê via `_nutrition()`.
- ✅ **Ingredientes humanos** — JÁ DERIVA. `_build_ingredients_text()` junta `RecipeItem.meta["label"]`
  por peso decrescente → `Product.ingredients_text`.
- ❌ **Alérgenos/dieta** — **A LACUNA REAL DO WP-7.** Hoje vivem só em `Product.metadata`
  (`allergens`/`dietary_info`) — stopgap que o WP-5 consome. `RecipeItem.meta` NÃO tem campos
  estruturais de alérgeno/dieta. ADR-008 adiou dietary de propósito (nutrientes = soma aritmética;
  alérgenos = união, exige flags no insumo + UI).

**Escopo WP-7 (o que falta), espelhando o padrão de `fill_nutrition_from_recipe`:**
1. Estender `RecipeItem.meta` (JSONField — sem migração) com `allergens: list[str]` e
   `dietary_info: list[str]` por insumo. Dataclass-driven (ver [[feedback_dataclass_driven_admin]]).
2. Novo serviço `aggregate_dietary_from_recipe(product)` em `shop/services/`: expande BOM (reusar
   `_expand_recipe_items`), faz **união** de alérgenos e resolve dietary (vegano/vegetariano = só se
   TODOS os insumos compatíveis; "sem X" = se NENHUM insumo tem X), grava em `Product.metadata`
   (auto_filled, respeita override manual — como nutrição).
3. Signal `post_save` em Recipe dispara junto com a nutrição (mesmo ponto).
4. Form admin no Craftsman p/ preencher allergens/dietary do `RecipeItem` (hoje JSON raw).
5. Seed: popular flags dos insumos da Nelson (hoje o seed põe direto no `Product.metadata`).
6. Testes do serviço (união/edge cases) + manter WP-5 funcionando (lê `Product.metadata`, que passa a
   ser derivado em vez de manual).
**Referências do Core:** `packages/craftsman/shopman/craftsman/models/recipe.py` (Recipe/RecipeItem),
`shop/services/nutrition_from_recipe.py` (padrão a espelhar), `packages/offerman/.../admin_unfold/
nutrition_form.py` (form do stopgap), ADR-008 `docs/decisions/adr-008-pdp-nutrition.md`.

---

## Tier 3 — dívida operacional (paralelo; omotenashi é prioridade)

### WP-8 — 🥇 Reconstruir o gate de browser-QA Omotenashi contra a loja Nuxt  ✅ CONCLUÍDO (2026-06-17) · ⏱ médio
O headless removeu o gate do CI (navegava páginas Django mortas). **Omotenashi é 1ª classe** → o gate
voltou, reescrito p/ a topologia real. Entregue:
- **Workflow dedicado** `.github/workflows/omotenashi-gate.yml` ("Omotenashi Gate"): Postgres +
  Python + Node + Chrome → `make omotenashi-browser-ci`; sobe screenshots/relatório/logs como artifact.
  (Comentário stale do `runtime-gate.yml` atualizado p/ apontar o novo workflow.)
- **Orquestração única** (`scripts/run_omotenashi_browser_ci.sh`) runnable local==CI: migrate + seed +
  **build/serve da loja Nuxt** (`127.0.0.1:3100`, BFF→Django) + Django (`:8001`) com
  `SHOPMAN_STOREFRONT_BASE_URL` apontando p/ a loja, QA browser estrita, teardown dos dois servidores.
- **Runner** (`run_omotenashi_browser_qa.mjs`): cookie de sessão QA gravado em **todas as origens** da
  matriz (Django + Nuxt); sessão = superusuário (operador) **+ order-access grants**
  (`shopman_order_access_refs`, via `order_ref` exposto na matriz) p/ os pedidos dos checks de
  pagamento/tracking — DRF não lê `request.user`, o acesso a pedido é por grant de sessão; helper
  `resolveNavigable` **pula honestamente** (log explícito, nunca falso-verde) superfícies não servidas;
  flag `auth_gated` (checkout) trata o gate de login como estado esperado, não bloqueio.
- **Matriz** (`omotenashi_qa.py`): POS repontado p/ `pos_links.pos_url()` (knob `SHOPMAN_POS_BASE_URL`),
  pulado até a fase C; novos campos `auth_gated` + `order_ref`.
- **Fixes reais que o gate surfaceou:** (a) `shop/services/kds.py` — qty de componente de bundle era
  `int * Decimal` → `Decimal` no JSONField do ticket (quebrava seed no SQLite; Postgres mascarava);
  agora `int()`. (b) `tracking/[ref].vue` + `pedido/[ref]/pagamento.vue` — não repassavam o cookie no
  SSR (igual às páginas de conta), então renderizavam o fallback "não encontrado" p/ um cliente que
  PODE ver o pedido; corrigido.
- **Verificado ao vivo:** `make omotenashi-browser-ci` → **12 pass, 0 review, 2 skipped (POS)**; os 3
  pedidos-cliente renderizam o estado REAL (PIX, expiração+recuperação, pronto p/ retirada), loja Nuxt
  + operador Django navegados.

### WP-9 — e2e Playwright + locustfile contra Nuxt/API  ✅ CONCLUÍDO (2026-06-17) · ⏱ médio
Os testes batiam em rotas Django de cliente aposentadas no cutover headless. Reescritos para a
superfície que existe de fato (loja Nuxt + API), mantendo os de operador (Django vivos) e pulando o
POS (migrou para seu próprio app Nuxt — fase C).

**Entregue:**
- **e2e** (`shop/tests/e2e/test_storefront_e2e.py`): fluxos de cliente (menu→PDP→carrinho→checkout,
  tracking, pagamento) contra a **loja Nuxt** com selectors UI-Thing; checkout trata o gate de login
  como guardrail esperado; order-scoped (tracking/pagamento) via **grant de sessão**
  (`shopman_order_access_refs`, mintado pelo conftest e setado como cookie). Operador (console de
  pedidos, KDS) segue em **Django**, autenticado por sessão de superusuário mintada. POS → `skip`
  explícito (fase C). Refs de cenário semeado reusam a **mesma matriz Omotenashi** (fonte única).
- **conftest** (`shop/tests/e2e/conftest.py`): `--store-base-url` (Nuxt :3100) + `--operator-base-url`
  (Django :8001); fixtures `grant_order_access`/`operator_session` mintam sessões via ORM **em thread
  separada** (a sync-API do Playwright mantém um event loop na thread do teste → `SynchronousOnlyOperation`).
- **orquestração** (`scripts/run_storefront_e2e.sh` + `make storefront-e2e`): espelha o gate WP-8 —
  seed + build/serve loja Nuxt :3100 (BFF→Django) + Django :8001, depois `pytest -m browser`. Browser
  E2E é **deselecionado por padrão** (`addopts -m 'not browser'` no pyproject) e re-selecionado só pelo
  script — `make test` não tenta subir browser.
- **locust** (`shop/tests/load/locustfile.py`): reescrito contra a **API Django** (`/api/v1/*`, rotas
  nomeadas e confirmadas no `storefront/api/urls.py`). Browsing/checkout aprendem SKUs reais do menu no
  `on_start` (auto-corrige vs seed); operador (console/KDS, Django vivos) com **login CSRF-aware**; cart
  `409` (conflito de estoque) tratado como resposta válida. O throttle anônimo (120/min por IP) virou
  env-configurável (`SHOPMAN_API_ANON_THROTTLE_RATE`) — produção mantém o guardrail; a carga sintética
  single-IP roda com ele desligado para medir o backend, não o throttle.

**Verificado ao vivo (2026-06-17):** e2e **17 passed / 1 skipped (POS)** com os dois servidores no ar;
locust headless 30s/-u30 → **0.00% fails** (333 reqs). `make test` 1844 + `make lint` verdes.
**Flagado (infra):** alvos de P95<500ms dependem de Postgres + workers reais (SQLite dev single-process
serializa o menu); medir em ambiente com infra — ver [[project_infra_wps_need_docker_validation]].

### WP-10 — Limpezas  ⏱ pequeno
- Podar emits de cliente mortos em `shop/handlers/_sse_emitters.py` (`stock-`/`order-` sem assinante),
  preservando os do operador (`backstage-*`).
- Atualizar/remover `.do/app.yaml` (staging path-routed, stale — staging agora é subdomínios).
- Cleanup agendado de device-trust expirado; revisar enforcement de `audience` do AccessLink na troca.

---

## Tier 1 (novo) — WP-11 — Fluxo final de ENTREGA  ⏱ grande · risco médio
> Pedido do Pablo (2026-06-17). Hoje a taxa de entrega vem do `DeliveryZone` (por CEP/bairro) como
> **modifier** no total. Falta o fluxo de entrega "para valer":

1. **Taxa por FAIXA DE DISTÂNCIA (admin-configurável).** Calcular a distância loja→endereço
   (já temos `Shop.latitude/longitude` + lat/lng no `delivery_address_structured`) e casar com faixas
   configuráveis (ex.: 0–2km=R$5, 2–5km=R$8, …). Modelo/admin novo (faixas) OU `Shop.defaults`
   dataclass-driven (ver `feedback_dataclass_driven_admin`). Coexistir/decidir vs `DeliveryZone`
   (CEP/bairro): distância pode ser a regra primária; CEP/bairro fallback.
2. **Frete explícito no pedido.** ~~Injetar como ITEM~~ → **DECIDIDO: campo dedicado** (`delivery_fee_q`,
   já first-class), mapeável a `vFrete` na NF-e. Não vira OrderItem (ver decisões travadas abaixo).
   WP-11 garante que apareça explícito no carrinho/checkout/tracking/fechamento.
3. **Facilitador "teleporte" de endereço (sem API).** O serviço de entrega usado hoje **não tem API**.
   Construir um facilitador OPERADOR que leva os dados de endereço do pedido para o site externo do
   serviço (pré-preencher via query params/deep-link, ou copiar campos estruturados p/ clipboard) —
   só para **reduzir erro de digitação**; o resto do despacho segue **manual** num primeiro momento.
   Provável superfície: ação no backstage (detalhe do pedido / KDS expedição). Definir o alvo (URL do
   serviço) com o Pablo.

### Decisões TRAVADAS (Pablo, 2026-06-17)
- **Taxa = motor de DISTÂNCIA; `DeliveryZone` rebaixada a EXCEÇÃO.** Faixa de distância (lat/lng,
  haversine loja→endereço) é o preço primário. A `DeliveryZone` (CEP/bairro) deixa de ser preço default e
  passa a ter dois modos: **`exclude`** ("não entrego aqui" → bloqueia) e **`override`** ("esse
  bairro/CEP é taxa fixa X, ignora o raio"). Default `override` mantém zonas semeadas funcionando.
  Ordem de resolução: exclusão de zona → override de zona → faixa de distância → (sem faixa/cobertura)
  `delivery_zone_error`.
- **Frete = CAMPO DEDICADO, NUNCA OrderItem.** Best-practice fiscal BR: frete é `vFrete` no bloco de
  transporte da NF-e/NFC-e, **não** linha de produto. Mantém o `delivery_fee_q` de primeira classe
  (já é assim: `DeliveryFeeModifier`→`CommitService`→tracking) — queryable, reconciliável, mapeável a
  `vFrete`. OrderItem sintético seria regressão (fere "Offerman=só vendáveis", polui estoque/KDS/picking,
  distorce a nota). WP-11 troca só a ORIGEM do valor (distância) e o torna explícito no checkout/tracking.
- **Teleporte = utilitário LOCAL Python** que preenche o form do serviço externo (DOM via
  Playwright/Selenium ou autotype), **clipboard como fallback**. Roda na máquina do operador (desacoplado
  do deploy). Pendente do Pablo: **URL + nomes dos campos** do serviço. Não bloqueia o backend.

### Slices de execução
1. **Backend distância (PRIMEIRO):** `Shop.latitude/longitude` (já existe) = origem; novo modelo
   `DeliveryDistanceBand` (faixas admin-configuráveis, espelha `DeliveryZone`); serviço haversine puro
   (`shop/services/delivery_distance.py`); `DeliveryZone.mode` (override/exclude); `DeliveryFeeModifier`
   reescrito p/ a ordem de resolução acima; adapter `match_distance_band`; seed (coords + faixas);
   `delivery_distance_km` em `session.data` p/ transparência no checkout (omotenashi). Testes.
2. **Camada visual** (checkout/tracking Nuxt): mostrar "X km · R$ Y" explícito; estados fora-de-área.
3. **Teleporte** (por último, quando o Pablo passar URL/campos): ação no backstage que dispara o
   utilitário local com os dados estruturados do endereço.

**Abertos p/ o Pablo (não bloqueiam o backend):** URL + campos do serviço de entrega; faixas de
distância iniciais (km→R$) p/ o seed.

---

## SEQUÊNCIA MESTRA (decidida 2026-06-17 — "fazer tudo")

**Fase A — camada visual Nuxt (WP-1..6): ✅ CONCLUÍDA** (commits `288fd141`→`0d5ddc8e`, inclui os
ajustes do Pablo: contraste do "Me avise", coração só na PDP). `make test` 1828 + `make lint` + vitest verdes.

**Fase B — dívida do storefront + entrega (ordem):**
1. **WP-7** ✅ — alérgenos/dieta via Recipe/BOM CONCLUÍDO (2026-06-17; nutrição+ingredientes+peso já eram do Core).
2. **WP-8** ✅ — gate de browser-QA Omotenashi contra a loja Nuxt + operador Django no CI CONCLUÍDO (2026-06-17; workflow dedicado, 12 pass/0 review/2 POS skipped).
3. **WP-9** ✅ — e2e Playwright + locustfile contra Nuxt/API CONCLUÍDO (2026-06-17; e2e 17 pass/1 POS skip, locust 0 fails; `scripts/run_storefront_e2e.sh` + `make storefront-e2e`).
4. **WP-11** — fluxo de entrega (taxa por distância + item + teleporte). **Coletar decisões do Pablo ao chegar**
   (taxa OrderItem real vs apresentação; distância vs DeliveryZone; URL do serviço + faixas iniciais).
5. **WP-10 resto** — podar SSE de cliente (no-op), `.do/app.yaml` stale, device-trust cleanup agendado,
   enforcement de `audience` do AccessLink na troca.

**Fase C — Revisão Reversa Spec-driven das outras superfícies** (mesmo método: ler código → spec →
caçar brechas → plano → executar):
6. **PDV (POS)** — `surfaces/pos-uithing-nuxt` + `shop/services/pos.py` + backstage POS.
7. **Backstage / KDS / produção / fechamento** — `shopman/backstage/`.
8. **Re-spec do storefront** pós-correções.

**Gate por WP:** `make test` + `make lint` (+ vitest p/ mudanças Nuxt) verdes; verificar UI no preview
(127.0.0.1:3000); commit por WP; copy via OmotenashiCopy; não mergear sem o Pablo. Cada chunk grande
(WP-7, WP-8, WP-9, WP-11, e cada superfície da fase C) pode virar uma sessão nova com prompt auto-contido.
