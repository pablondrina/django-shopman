# ADMIN-ROLE-PLAN — Admin vira CRUD mínimo + configurações

> Mandato (Pablo, 2026-07-17): "vamos diminuir o admin a CRUD mínimo e
> configurações". Execução operacional migra para os apps Nuxt do backstage;
> o Admin/Unfold passa a cumprir bem um único papel: cadastro e configuração.
>
> Etapas com aprovação entre elas: (1) inventário ✅ aprovado em 2026-07-17;
> (2) este plano de migração ✅ decisões travadas em 2026-07-17 (abaixo);
> (3) UX de configuração do que fica (capítulo próprio, após aprovação).

## Decisões travadas (Pablo, 2026-07-17)

1. **Fechamento do dia mora na ANTESALA do PDV** (pos-nuxt, rota `/session`),
   não no Gestor. Honra o pedido registrado da antesala estilo Odoo POS
   (lobby de sessão pré-venda): abrir/fechar caixa, sangria/suprimento,
   relatórios X/Z, histórico de turnos — e o fechamento do dia (contagem cega
   de sobras, D-1, perdas) entra nesse mesmo ritual de fim de dia. A migração
   do fechamento vira parte da feature da antesala e resolve os dois mandatos
   de uma vez.
2. **Console Admin de produção migra e some** — reverte explicitamente a
   decisão de 2026-06-25 ("fichas/relatórios/pesagem/compromissos ficam no
   Admin"). O mandato novo prevalece; auditoria de paridade primeiro.
3. **As 5 corretivas FICAM no Admin**, gated por permissão: reembolso payman,
   executar Directive, liberar Hold, recalcular Quant, completar checklist
   run. São ferramentas raras de exceção, papel legítimo do backoffice
   restrito. Reavaliáveis caso a caso no futuro.

## Estado de partida (síntese do inventário)

Já saíram do Admin (registrado em `scripts/check_unfold_canonical.py`): fila de
pedidos (→ orders-nuxt/Gestor), KDS (→ kds-nuxt), POS (→ pos-nuxt), execução de
produção e modais de escassez (→ production-nuxt/Fournil).

Execução que ainda vive no Admin:

| # | Superfície | Cobertura Nuxt existente |
|---|---|---|
| 1 | Fechamento do dia (`admin_console/closing.py`, única página custom que muta estado) | API pronta: `GET/POST /api/v1/backstage/closing/` (mesma projection `build_day_closing` + mesmo service `perform_day_closing`, mesma perm `backstage.perform_closing`) — sem UI |
| 2 | Console de produção, 6 views GET-only (`admin_console/production.py`: painel, planejamento, produção, relatórios+CSV, pesagem, compromissos) | Fournil já tem `/plan`, `/board`, `/mise-en-place`, `/expedite` e **pesagem** (`useWeighing`, `WeighingLabels`, API `production/weighing/`) |
| 3 | Admin actions que duplicam apps Nuxt: Order avançar/cancelar; Session commit/resolve/run-check; WorkOrder concluir/anular | Gestor (fila + ações), POS (venda/comanda), Fournil (start/finish/void via API `production/<id>/*`) |
| 4 | `CashMovementAdmin` add-only (sangria/suprimento/ajuste) | PDV já cobre: `PosCashPanel` (open/close/sangria/suprimento) sobre `pos/cash/*` |
| 5 | `OperatorAlertAdmin` ack (bulk + row) | Gestor já cobre: `AlertsBell`/`useAlerts` sobre `alerts/` + `alerts/<pk>/ack/` |
| 6 | Dashboard `/admin/` com widgets de operação ao vivo (deep-links p/ pedidos e WOs) | Gestor é o painel operacional |

Backend da antesala que já existe (verificado no inventário + memória):
`CashShift`/`CashMovement`/`POSTerminal` + `services/cash.py` + endpoints
`pos/cash/{open,close,close-blocking,movement}`; o POS já bloqueia venda sem
turno (`requires_open_shift_for_sale`). O que falta é a SUPERFÍCIE de lobby e
o read model de X/Z.

## Work packages (auto-contidos, 1 PR por WP)

### WP-ADM-1 — Antesala do PDV: lobby de sessão

Escopo: pos-nuxt ganha a rota `/session` que gateia a venda (estilo Odoo POS).

- Sem turno aberto → operador cai na antesala; com turno → "Continuar
  vendendo" + ações de sessão.
- Abrir caixa (valor de abertura), fechar caixa (contagem cega), sangria/
  suprimento migram dos diálogos espremidos (`PosCashPanel`/`cashDialogOpen`)
  para a antesala. Backend existente `pos/cash/*`; sem endpoint novo.
- Desktop-first, design neutro do operador; presentation pura + vitest.
- Aceite: fluxo abrir→vender→movimento→fechar em staging; venda continua
  bloqueada sem turno; vitest verde.

### WP-ADM-2 — Fechamento do dia na antesala

Pré-requisito: WP-ADM-1.

- Seção/rota `/session/closing` consumindo `GET/POST
  /api/v1/backstage/closing/`, visível só com `backstage.perform_closing`
  (Gerente) — a antesala mostra a entrada; o gate é da API.
- Paridade com a tela Admin: produção pendente (com atrasadas + link p/
  Fournil), produção do dia (planejado/feito/perda), encomendas dos próximos
  dias, discrepâncias (vendido/disponível/déficit), contagem cega por SKU,
  estado `already_closed` ("Fechado por X às HH:MM"), aviso de D-1 velho.
  ⚠️ "D-1" é jargão interno — label visível é "Ontem".
- Badges derivadas de `classification` na presentation do app — **não**
  consumir `badge_css`/`badge_label` da projection (Tailwind do Admin
  vazando; remoção no WP-ADM-8).
- Confirmação explícita antes de registrar (ação irreversível → modal).
- Fora do v1: link de CSV de produção (fica na superfície de relatórios até o
  WP-ADM-7).
- Aceite: vitest da presentation; QA em staging com a tela Admin ainda viva
  (dupla superfície é segura: service idempotente, 409 em `already_closed`).

### WP-ADM-3 — Cutover do fechamento

Pré-requisito: WP-ADM-2 no ar e validado.

- Sidebar Admin: item "Fechamento" passa a apontar para
  `SHOPMAN_POS_BASE_URL/session/closing` (padrão dos itens que linkam apps
  Nuxt: só aparece com a URL setada).
- Remover `admin_console/closing.py`, `DayClosingForm`, templates
  `admin_console/closing/` e a rota `admin/operacao/fechamento/`
  (`config/urls.py`). Zero residuals.
- Registry do gate: remover `admin-console-day-closing` de
  `CANONICAL_ADMIN_SURFACES`; `projections/closing.py` passa à superfície
  `headless-operator-api`.
- `DayClosingAdmin` (readonly, auditoria) permanece.
- Docs: `docs/guides/day-closing.md` (nova casa), `docs/guides/rbac-personas.md`
  (aproveitar e corrigir as rotas mortas de pedidos/KDS).
- Aceite: `make admin` + `make test-framework` verdes; env
  `SHOPMAN_POS_BASE_URL` conferido na spec LIVE do DO.

### WP-ADM-4 — Relatórios X/Z e histórico de turnos na antesala

Não bloqueia o cutover (WP-ADM-3); completa a antesala.

- Novo read model: leitura X (parcial do turno aberto), Z (fechamento do
  turno), histórico de turnos/vendas do dia — projection nova em
  `backstage/projections/` (chaves em inglês) + endpoint sob `pos/cash/`.
- Impressão térmica fica fora (entra com o capítulo NFC-e).
- Aceite: vitest + testes de API do backstage.

### WP-ADM-5 — Poda de actions duplicadas (pedidos, sessões, work orders)

Independente; pode correr em paralelo (worktree isolado).

- orderman `OrderAdmin` (Unfold): remover `advance_status_row`,
  `cancel_order_row`, `advance_selected_status`, `cancel_selected`.
- orderman `SessionAdmin`: remover `action_commit` e as views custom
  `resolve_issue_view`/`run_check_view`.
- craftsman `WorkOrderAdmin` (Unfold): remover `close_wo_row`, `void_wo_row`,
  `finish_selected_work_orders`, `void_selected_work_orders`; manter as
  row-actions de navegação (`production_board_row`, `commitments_row`).
- Onde mexer: nas versões `contrib/admin_unfold` (opt-in da suíte). Os
  fallbacks Django puros dos packages mantêm suas actions (história
  standalone dos apps pip; drift deliberado, documentado no contrib tocado).
- `Directive` mantém `execute_*` (corretiva — decisão 3).
- Aceite: testes dos packages tocados + `make test-framework`; conferir que o
  Gestor cobre cancelamento com justificativa e avanço.

### WP-ADM-6 — Caixa e alertas viram trilha readonly

Independente; caixa idealmente após WP-ADM-1 (antesala é a casa nova).

- `CashMovementAdmin`: `has_add_permission=False` (PDV cobre sangria/
  suprimento/ajuste; conferir paridade do kind `ajuste` — se o PDV não expõe,
  expõe no mesmo WP).
- `OperatorAlertAdmin`: remover `mark_acknowledged`/`acknowledge_row`; ack é
  do Gestor (`AlertsBell`). Changelist readonly permanece como trilha;
  "Alertas ativos" da sidebar vira consulta de auditoria (badge avaliado).
- Aceite: `make admin`; QA rápido de sangria no PDV staging.

### WP-ADM-7 — Console de produção sai do Admin (fatiado)

- **7a — auditoria de paridade** (curta, sem código): matriz view-a-view do
  que `admin_console/production.py` mostra vs Fournil/Gestor. Hipótese:
  gaps = relatórios+CSV, KPIs do painel, compromissos por WO; pesagem já
  existe no Fournil. Saída: escopo fechado de 7b/7c aprovado por Pablo.
- **7b — relatórios no Fournil**: rota `/reports` (inglês), endpoint headless
  `production/reports/` serializando `build_production_reports` (chaves em
  inglês), CSV pelo mesmo endpoint, presentation pura + vitest. KPIs do
  painel entram se 7a confirmar que o board não os cobre.
- **7c — compromissos por WO no Fournil** (se 7a confirmar gap): visão
  read-only consumindo `order_commitments_for_work_order`.
- **7d — remoção**: apagar as 6 views + templates `admin_console/production/`,
  rotas `admin/operacao/producao/*`, superfície `admin-console-production` do
  registry, links das `TABS` do craftsman e itens da sidebar (grupo
  "Produção" passa a linkar Fournil + Fichas técnicas). `projections/
  production.py` migra à superfície headless. Helpers compartilhados órfãos
  (`views/production.py`, partials de escassez) morrem junto — zero
  residuals. Docs e exemplo `make admin url=` no CLAUDE.md atualizados.

### WP-ADM-8 — Dashboard e faxina final

Por último (depende dos cutovers).

- Dashboard `/admin/`: remover widgets de operação ao vivo (pedidos, WOs);
  reforçar papel de config — saúde da copy omotenashi, atalhos de
  configuração, resumo de auditoria. Insumo direto da etapa 3.
- Projection de closing: remover `badge_css`/`badge_label` (presentation
  leakage) — depende do WP-ADM-3.
- Sidebar: grupo "Operação ao vivo" só com links para os apps Nuxt + badges.
- Mortos: templates duplicados `packages/orderman/.../templates/ordering/admin/`;
  `ShopAdminWithBackstageURLs` (re-registro sem comportamento);
  `inject_simulated_ifood_order` vira management command
  (`inject_ifood_order`, DEBUG-only).
- Docs: `docs/reference/system-spec.md` (rotas Admin mortas).

## Ordem e dependências

```
WP-ADM-1 ──► WP-ADM-2 ──► WP-ADM-3 ──► WP-ADM-8 (item projection)
                     └──► WP-ADM-4 (não bloqueia o cutover)
WP-ADM-5 (independente, paralelo)
WP-ADM-6 (independente; caixa após WP-ADM-1)
WP-ADM-7a ──► 7b/7c ──► 7d
WP-ADM-8 por último
```

Fechamento primeiro (WP-1→3), conforme mandato; a antesala é o veículo.

## Riscos e salvaguardas

- **Gate canônico**: toda remoção de superfície exige atualizar o registry em
  `scripts/check_unfold_canonical.py` no mesmo PR; `make admin` é o aceite de
  cada WP que toca Admin.
- **Perms intactas**: nenhum WP muda permissões (`perform_closing`,
  `operate_pos`, etc.) — só a superfície onde a ação acontece. A antesala usa
  os gates existentes.
- **Transição do fechamento**: dupla superfície é segura (service idempotente,
  409 em `already_closed`); cutover só depois de QA em staging.
- **Deploy**: env `SHOPMAN_POS_BASE_URL`/`SHOPMAN_PRODUCTION_BASE_URL` são
  config da spec LIVE do DO (não do repo) — conferir no cutover.
- **Core sagrado**: nenhum WP toca models/services dos packages; só camada de
  admin (`contrib/admin_unfold`) e superfícies.
- **Antesala**: WP-1/2 mudam o fluxo de entrada do PDV — QA físico com a
  operação antes do cutover (o PDV é desktop-first e usado no balcão).

## Etapa 3 (após aprovação deste plano)

UX de configuração do que fica: navegação chave↔tela da copy omotenashi (por
superfície/momento, achável a partir do que o operador vê), e o que mais o
Admin precisa para cumprir bem o papel de configuração (RuleConfig,
NotificationTemplate, pickup_slots, cancellation_presets…). Capítulo próprio,
escrito após o OK da etapa 2.
