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

### WP-7 — Dados da PDP: ingredientes + nutricional + peso junto ao preço  ⏱ pequeno-médio
`project_pdp_data_fields_pending`: peso já existe (`Product.unit_weight_g`) — só exibir junto ao preço
(hoje enterrado no accordion). **DECIDIDO:** ingredientes/nutricional **derivam da Recipe/BOM** (Craftsman) — sempre o correto, sem
duplicar dado no `Product`. (Insumos com ficha técnica → tabela nutricional derivada; ingredientes
da BOM em texto humano pt-BR.) WP-5 (atributo dietético) também sai daí.

---

## Tier 3 — dívida operacional (paralelo; omotenashi é prioridade)

### WP-8 — 🥇 Reconstruir o gate de browser-QA Omotenashi contra a loja Nuxt  ⏱ médio
O headless removeu o gate do CI (navegava páginas Django mortas). **Omotenashi é 1ª classe** → o gate
volta, reescrito p/ subir a loja Nuxt no CI e navegar a matriz Omotenashi (a matriz em
`backstage/services/omotenashi_qa.py` já aponta p/ `storefront_links`/loja). Restaura cobertura de
acolhimento na superfície que de fato existe.

### WP-9 — e2e Playwright + locustfile contra Nuxt/API  ⏱ médio
`shop/tests/e2e/test_storefront_e2e.py` (cenários 01/02/06) e `shop/tests/load/locustfile.py` batem em
rotas Django legadas. Reescrever os de cliente contra a loja Nuxt/API; manter os de operador.

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
2. **Injetar a taxa como ITEM do pedido.** Hoje é `delivery_fee_q` (modifier/total). Pablo quer a
   entrega como **linha** do pedido (visível no carrinho/KDS/fiscal). DECISÃO: linha real (OrderItem
   sintético) vs linha só de apresentação. Cuidar de fiscal/totais/estoque (item não-estocável).
3. **Facilitador "teleporte" de endereço (sem API).** O serviço de entrega usado hoje **não tem API**.
   Construir um facilitador OPERADOR que leva os dados de endereço do pedido para o site externo do
   serviço (pré-preencher via query params/deep-link, ou copiar campos estruturados p/ clipboard) —
   só para **reduzir erro de digitação**; o resto do despacho segue **manual** num primeiro momento.
   Provável superfície: ação no backstage (detalhe do pedido / KDS expedição). Definir o alvo (URL do
   serviço) com o Pablo.

**Abertos p/ o Pablo:** qual serviço de entrega (URL/forma de deep-link); faixas de distância iniciais;
taxa como OrderItem real ou apresentação; relação distância × DeliveryZone (CEP/bairro).

---

## Ordem sugerida & gates

1. **WP-1** (correção real, rápida) → 2. **WP-2** (destrava WP-3/WP-5) → 3. **WP-3** + **WP-5** + **WP-4**
   (features de cliente) → 4. **WP-8** (omotenashi de volta ao CI) em paralelo → 5. **WP-6/WP-7**
   (polish) → 6. **WP-9/WP-10** (dívida).
`make test` + `make lint` verdes a cada WP. Cada feature nasce com teste + copy omotenashi.

## Depois: retomar a Revisão Reversa Spec-driven
Aplicar o mesmo método (ler o código → spec → caçar brechas) às outras superfícies: **PDV**,
**backstage/KDS/produção/fechamento**, e re-spec do storefront pós-correções.
