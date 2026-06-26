# GESTOR-PEDIDOS-PLAN — Gestor de pedidos ao estado da arte

> Redesign da superfície operacional de pedidos (`surfaces/orders-uithing-nuxt`)
> ao nível de benchmark. Frente **v1** (Onda 1 — núcleo de operação) do
> [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md). Prioridade declarada do Pablo.

**Status**: 🟢 **v1 COMPLETO — Arcs 1–5 entregues (2026-06-26)**, não commitado. Pendente: QA de
browser ao vivo (lote/staging). Arc 6 (analytics) = pós-v1.

**Decisões do Pablo:**
- **Benchmark = híbrido**: board limpo (Shopify) como padrão + view-mode de tabela densa
  (STORES) sob demanda.
- **Analytics (Arc 6) = pós-v1**. v1 = Arcs 1–5.
- **Convergência (matar board legado do `backstage-nuxt`) = no item separado** *Surface
  convergence* do backlog, não neste plano. Este plano foca só na app dedicada.

---

## Estado atual (mapeado do código)

**Superfície ativa**: `surfaces/orders-uithing-nuxt`
- Board 3 zonas (Entrada / Preparo / Saída) — `app/pages/index.vue`,
  `app/composables/useOrdersBoard.ts`, `app/presentation/board.ts`.
- Detalhe full-page — `app/pages/[ref].vue`, `app/composables/useOrderDetail.ts`.
- Realtime: SSE `/gestor/events/orders/` + polling 30s.

**Superfície legado (duplicada)**: `surfaces/backstage-nuxt` (`app/pages/pedidos/`)
— tabela com filtro de canal + view-mode grid/table + detalhe em slideover. É o
"hub" genérico antigo. **Convergência**: descontinuar os pedidos daqui (overlap
com o item *Surface convergence* do backlog v1).

**Camada de dados (Django, fonte única — sagrada, não duplicar)**:
- Projections: `shopman/backstage/projections/order_queue.py`
  (`OrderCardProjection`, `OperatorOrderProjection`, `TwoZoneQueueProjection`,
  `AwaitingWorkOrderProjection`, timeline, itens).
- API/ações: `shopman/backstage/api/operations.py` (queue, detail, advance,
  confirm, reject, cancel, settle delivery cash, requeue fiscal, notes).

**O que já funciona**: listar por zona, busca (ref/cliente/itens), timer com SLA
(3 níveis), realtime, ações inline (confirm/advance/reject/settle), detalhe rico
(timeline, itens, notas internas, links fiscais, presente), produções em espera,
tema claro/escuro, responsivo.

> Implicação: a maior parte do trabalho é **UI + comportamento no Nuxt**, com
> ajustes pontuais de projection/endpoint quando faltar um campo. Core é sagrado.

---

## Gaps vs. benchmark (Shopify/STORES/Take.app)

Triados por valor operacional real numa padaria sob pressão:

1. **Filtros + ordenação + view-mode** — hoje só busca textual. Falta filtro por
   canal/status e sort (elapsed/total/status). Legado já tem o padrão.
2. **Razões de blocagem honestas** — quando `advance` falha (ex.: produção em
   falta), a UI mostra erro genérico. Operador precisa do *porquê* acionável.
3. **Alertas integrados** — `/api/v1/backstage/alerts/` existe no backend e não é
   consumido; falta badge/sino no header do board.
4. **Atalhos de teclado** — velocidade de bancada (confirmar/avançar/recusar).
5. **Bulk actions** — selecionar vários + ação em lote (ex.: confirmar Entrada).
6. **Atribuição de operador** — "estou atendendo este" para evitar choque.
7. **Comentário no timeline + export/impressão** — anotação visível e imprimir/CSV.
8. **Analytics de operação** (nice-to-have, possivelmente pós-v1) — SLA por
   status/canal, tempo médio.

---

## Arcos propostos (cada um = commit verificável ao vivo)

> Padrão dos redesigns anteriores (POS/KDS/storefront): TS puro em
> `app/presentation/` testável (vitest), UI fina, verificar ao vivo + console
> limpo por arco. Desktop-first (superfície de operador), mas responsivo.

- **Arc 1 ✅ (2026-06-26) · Triagem power-user (híbrido)** — filtro por canal
  (chips derivados dos dados) + ordenação (Chegada/Urgência/Mais recentes,
  persistida em cookie) + **view-mode board limpo (padrão) ↔ tabela densa**
  (persistido). Lógica pura em `app/presentation/board.ts`
  (`channelOptions`/`matchesChannel`/`sortCards`/`triageCards`/`flattenZones`),
  vitest **28 verdes**; UI em `app/pages/index.vue`. Typecheck limpo nos arquivos
  tocados. **Pendente: QA de browser ao vivo** (precisa Django+seed+gestor+auth).
- **Arc 2 ✅ (2026-06-26) · Feedback honesto de ação** — raiz no backend:
  `advance_order` ([orders.py](../../shopman/backstage/services/orders.py)) engolia
  o motivo (`OrderError("Ação inválida")`); agora surfaceia `str(exc)` (a razão de
  `advance_block_reason`), como confirm/reject já faziam (teste reforçado em
  `test_orders_service.py`). Front: erro **persistente e inline** por pedido no
  card e numa sub-linha da tabela (não só toast transiente) —
  `actionError`/`clearActionError` no composable.
- **Arc 3 ✅ (2026-06-26) · Consciência operacional** — o sino de alertas
  (`AlertsBell` + `useAlerts`, badge + ack) **já existia e está completo**. Adicionado
  o que faltava: **atalhos de teclado** (`/` busca · `r` atualizar · `v` view ·
  `s` ordenar · `Esc` limpar) com resolver puro testado, guarda de digitação e
  dicas nos controles.
- **Arc 4a ✅ (2026-06-26) · Trabalho em lote** — seleção múltipla (checkbox no
  card e na tabela + selecionar-todos-visíveis) + barra de ação batch
  (Confirmar/Avançar só os elegíveis, via `bulkableRefs` puro testado + `actMany`
  no composable que posta tudo e refresca uma vez).
- **Arc 4b ✅ (2026-06-26) · Atribuição de operador** — "estou atendendo" em
  `Order.data["assignment"]` (sem migração). Backend: `assign_order`/`unassign_order`
  em operator_orders + facade + endpoints assign/unassign + campo
  `assigned_operator` na `OrderCardProjection` + registro em data-schemas
  (roundtrip testado). Front: toggle atender/liberar no card e na tabela + chip do nome.
- **Arc 5 ✅ (2026-06-26) · Registro + saída** — **export CSV + imprimir** da fila
  triada (`rowsToCsv` puro testado + `print:hidden` no chrome) + **comentário no
  timeline** (OrderEvent `operator_comment` → endpoint comment + compositor no
  detalhe; timeline já renderiza eventos; label pt-BR "Comentário"; testado).
- **Arc 6 · Analytics** — ⏭️ **pós-v1** (decisão Pablo). Painel de SLA/tempo médio
  por canal/status.
- **Convergência** — ⏭️ tratada no item *Surface convergence* do backlog (não
  neste plano).

---

## Invariantes

- **Core é sagrado**: regras/estados/ações continuam no Django; Nuxt só traduz.
  Campos contextuais novos vão em `Order.data` (sem migração), registrados em
  [data-schemas.md](../reference/data-schemas.md).
- **Não duplicar projection**: estender `order_queue.py` quando faltar campo, não
  recalcular no front.
- **Voz e acessibilidade**: copy de operador clara; alvo desktop-first sem perder
  o responsivo; contraste alto.
- **Não commitar** o `nuxt.config.ts` com `allowedHosts` de túnel (dev).

---

## Referências

- [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md) · [SURFACE-CONVERGENCE-PLAN](SURFACE-CONVERGENCE-PLAN.md)
- `surfaces/orders-uithing-nuxt/` — superfície ativa
- `shopman/backstage/projections/order_queue.py` · `shopman/backstage/api/operations.py`
