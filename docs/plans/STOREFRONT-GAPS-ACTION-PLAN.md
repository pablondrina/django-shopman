# STOREFRONT-GAPS — plano de ação (pós revisão reversa)

> **Origem.** Saiu da revisão às avessas em [`docs/reference/storefront-spec.md`](../reference/storefront-spec.md)
> (seção 6, Gaps). Cada WP é auto-contido: problema → contexto recuperado → abordagem proposta
> (simples · robusta · elegante) → decisões abertas p/ o Pablo → esforço/risco. Princípios do projeto
> valem (omotenashi first-class, zero gambiarra, respeitar o Core, confirmar UX cedo/inline).
>
> Depois de atacar (ou priorizar) estes, **retomamos a Revisão Reversa Spec-driven** para as outras
> superfícies (PDV, backstage/KDS) e/ou re-spec do storefront pós-correções.

## Princípio transversal: Omotenashi é passageiro de 1ª classe

O headless **removeu do CI o gate de browser-QA Omotenashi** (ele navegava as páginas Django, mortas).
Não pode ficar sem. **WP-8 reconstrói esse gate contra a loja Nuxt** — é pré-requisito de "pronto",
não follow-up opcional. Toda feature abaixo nasce com copy via `OmotenashiCopy`/catálogo e estados
acolhedores (informar, nunca bloquear seco).

---

## Tier 1 — impacto direto no cliente

### WP-1 — Checkout volta a persistir endereço/cliente/defaults  ⏱ pequeno · risco baixo
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

### WP-2 — Revisão do vocabulário de disponibilidade  ⏱ médio · risco baixo
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

### WP-3 — "Me avise quando disponível" (ativo, WhatsApp)  ⏱ médio-grande · risco médio · 🥇 ouro
**Contexto recuperado (`project_notify_me_pending`).** Desenho já decidido (2026-04-18):
- Modelo `StockAlertSubscription(sku, channel, contact/customer, subscribed_at, notified_at)`.
- Disparo: signal de Stockman `Move` quando `ready` passa de 0 → positivo (reusar o caminho de
  `on_holds_materialized`/`stock.arrived` que já existe — WP-AV-12).
- UI: CTA na PDP **só** no estado `UNAVAILABLE` sem plano (WP-2 garante que esse estado é honesto).
- Notificação respeita prefs do Guestman (ManyChat→WhatsApp; email pro resto) — reusa
  `shop/services/notification.py` + magic link da loja.
**Abordagem.** Slice fino: modelo + subscribe endpoint (`POST /api/v1/availability/<sku>/notify/`) +
resolver de "ready 0→+" no signal + template de notificação `stock_back`. CTA na PDP Nuxt.
**DECIDIDO:** anônimo **pode** se inscrever (só telefone/WhatsApp) — reduz fricção; valida via o
mesmo OTP se virar pedido.

### WP-4 — Favoritos + expansão de coleções dinâmicas  ⏱ médio-grande · risco médio
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

### WP-5 — Política de preferências alimentares (avisar, opcionalmente filtrar)  ⏱ médio · risco baixo
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

### WP-6 — "Talvez você também goste" na PDP  ⏱ pequeno
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

## Ordem sugerida & gates

1. **WP-1** (correção real, rápida) → 2. **WP-2** (destrava WP-3/WP-5) → 3. **WP-3** + **WP-5** + **WP-4**
   (features de cliente) → 4. **WP-8** (omotenashi de volta ao CI) em paralelo → 5. **WP-6/WP-7**
   (polish) → 6. **WP-9/WP-10** (dívida).
`make test` + `make lint` verdes a cada WP. Cada feature nasce com teste + copy omotenashi.

## Depois: retomar a Revisão Reversa Spec-driven
Aplicar o mesmo método (ler o código → spec → caçar brechas) às outras superfícies: **PDV**,
**backstage/KDS/produção/fechamento**, e re-spec do storefront pós-correções.
