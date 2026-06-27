# KDS → Nuxt/UI-Thing — Kickoff (migração de superfície)

> ## ✅ CONCLUÍDO (2026-06-11)
>
> Superfície KDS migrada e redesenhada por inteiro em `surfaces/kds-uithing-nuxt`:
> **estação (operador) + picker + expedição + board do cliente**. Arcos 1–5 entregues,
> mais um ciclo de redesign first-shelf e ações de operador. Commits:
> - `539b861a` — redesign: card vertical altura-uniforme, paleta neutra (cor só na
>   urgência: tint ton-sur-ton do "próximo" + barra time-to-SLA), toque otimista
>   (fila serial + reconciliação), busca, grade auto-fill retrato, relógio, tira
>   "A fazer", tema, ícone garfo-e-faca, Material→lucide.
> - `dcab30fc` — ações do operador: **recall** (desfazer finalização; core
>   `reopen_ticket` + projection `recent_done` + painel "Concluídos") e **reconhecer
>   cancelado** (`KDSTicket.acknowledged_at`, migration 0012, botão "Ciente");
>   **volumes** em destaque na expedição.
> - `fee1a7fb` — polish: tela do cliente (painel de chegadas, código grande, "ao
>   vivo", transições) + picker (badge neutro, ícone de picking correto).
>
> Verificado: vitest 13, 349 testes backstage + 918 shop verdes, `nuxt build` limpo,
> ao vivo (dark/light) console limpo. Realtime: SSE same-origin (prod) + poll 15s (dev).
>
> **Decisões do kickoff (§6) resolvidas:** (b) copiar/adaptar a base do PDV; **endpoints
> fixos** no write-side (+ `recall`/`acknowledge`); porta dev :3003.
>
> **Pendente (escopo do Pablo, tocam lifecycle Core):** ações de operador 86/marcar
> indisponível, priorizar/rush, quantidade parcial. Descomissionar o KDS-HTMX (§5).
> Deploy staging.
>
> ---

> Plano de arcos da migração do **KDS** (Kitchen Display) da geração HTMX/gestor para
> Nuxt/UI-Thing, ratificada pelo Pablo em 2026-06-11 (WP3 do
> [SURFACE-CONVERGENCE-PLAN](SURFACE-CONVERGENCE-PLAN.md)). Espelha o processo que
> funcionou no PDV (WP7): **dado→contrato→apresentação→shell**, iterativo, verificando
> ao vivo, commit por arco. Sob o contrato headless (adr-012/014): a superfície
> renderiza intent; o orquestrador decide.

## 0. O que JÁ existe (de-risca muito)

Diferente do PDV (que precisou do drain S4/CQRS), **o KDS já é headless-ready**:

- **API JSON canônica** — `shopman/backstage/api/kds.py`:
  - `GET  /api/v1/backstage/kds/` → instâncias (picker)
  - `GET  /api/v1/backstage/kds/<ref>/` → **board da estação** (KDSBoardProjection)
  - `POST /api/v1/backstage/kds/tickets/<pk>/items/` → toggle item conferido
  - `POST /api/v1/backstage/kds/tickets/<pk>/done/` → finalizar ticket
  - `POST /api/v1/backstage/kds/expedition/<pk>/action/` → despachar/completar
  - `GET  /api/v1/backstage/kds/cliente/` → board do cliente (retirada)
- **Projeções limpas** (`projections/kds.py`): KDSItem/Ticket/ExpeditionCard/
  InstanceSummary/Board/CustomerOrder/CustomerStatus — frozen dataclasses + `build_*`.
- As views HTMX (`views/kds_station.py`, `kds_customer.py`) renderizam templates a
  partir DESSAS projeções — ou seja, o Nuxt consome a mesma fonte de verdade.

**Implicação:** o trabalho é majoritariamente **apresentação + shell + realtime**, não
backend. O Arc 1 vira verificação/endurecimento de contrato, não um build.

## 1. Desafios específicos do KDS (vs PDV)

- **Realtime via SSE é o coração** (não polling): tickets entram em tempo real, beep
  no novo, timers correndo, status mudando. O PDV não tinha isso. Precisa de
  integração SSE no Nuxt (EventSource → estado reativo + reconexão + degradação).
- **Cor é FUNCIONAL e first-class** (status do ticket, urgência do timer) — manter o
  semáforo, neutro só no chrome (já é a régua que aplicamos no KDS HTMX).
- **Multi-superfície:** estação (operador) + picker + expedição + **board do cliente**
  (customer-facing — base compartilhável com a futura tela-do-cliente-do-PDV).
- **Contrato de escrita:** hoje a API usa **endpoints fixos** (items/done/action), não
  o padrão Action-affordance do PDV. Decidir no Arc 1: manter endpoints fixos
  (simples, KDS tem poucas ações) ou trazer Actions (consistência com o PDV). Recomendo
  **endpoints fixos** — o KDS tem um verbo por gesto, Actions seriam over-engineering.

## 2. Reuso do design system do PDV (decisão de arquitetura)

O PDV (`pos-uithing-nuxt`) estabeleceu ouro reutilizável: `app/presentation/` (cut
dado→tela), `server/utils/djangoProxy.ts`, `app/components/Ui/` (UI-Thing), o
`PosFunctionRail`, os tokens neutros + escala (`tailwind.css`). O KDS Nuxt deve
**reaproveitar**, não reinventar. Opções (decidir no kickoff):
- **(a) Workspace/monorepo** — pacote compartilhado (`surfaces/shared/`) com tokens +
  Ui + rail + djangoProxy. Mais limpo, mais setup.
- **(b) Copiar/adaptar** — bootstrap do KDS copiando a base do PDV. Rápido, duplica.
- **Recomendação:** começar **(b)** (velocidade, o KDS tem necessidades próprias de
  layout), e extrair pra **(a)** quando a 3ª superfície (storefront) confirmar o padrão.

## 3. Arcos (proposta)

> Ordem dado→contrato→apresentação→shell, como no PDV. Commit por arco, verificação ao
> vivo (preview + dados reais via SSE).

- **Arc 1 — Contrato & scaffold.** Verificar/endurecer a API KDS (shape do board,
  enums de status, contrato de escrita; drift-guard se preciso). Bootstrap do
  `surfaces/kds-uithing-nuxt` (Nuxt + UI-Thing + tokens/escala do PDV + djangoProxy +
  proxy da API KDS). Decidir reuso (a/b) + endpoints-fixos vs Actions.
- **Arc 2 — Presentation TS + Board da estação (read + SSE).** `app/presentation/`
  do KDS (board→tela: ordenação, agrupamento, estado do timer, semáforo). Tela da
  estação consumindo `GET kds/<ref>/` + **SSE realtime** (EventSource → refresh
  reativo; beep no novo ticket; reconexão). É o núcleo.
- **Arc 3 — Write-side (gestos do operador).** Conferir item, finalizar ticket,
  despachar/completar (expedição) via os endpoints. Optimistic + reconciliação pelo
  refresh. Permissões (operador).
- **Arc 4 — Picker + Board do cliente.** Picker de estações; **customer board**
  (display de retirada, dark, leitura à distância) — base compartilhável com a
  tela-do-cliente-do-PDV ([[project_pos_customer_display]]).
- **Arc 5 — Shell visual & fidelidade.** Aplicar o design system do PDV (rail
  dark-spine, cards, escala), responsivo p/ telas de cozinha (grandes), impressão/
  kitchen-ticket se aplicável, polish.

## 4. Gates (por arco, como no PDV)
- De dentro de `surfaces/kds-uithing-nuxt`: `npx nuxi typecheck` + `npx vitest run`
  (presentation TS pura testada).
- Backend (se tocar): `pytest shopman/backstage/tests -q` (KDS API/projeções).
- **Verificação ao vivo** com SSE real (dados de cozinha) — o realtime é o risco-chave.

## 5. Saída / descomissionar o HTMX
Quando o Nuxt KDS cobrir estação+picker+customer-board com paridade verificada, o KDS
HTMX (`runtime/kds_*`, `gestor/producao/kds.html`) e sua base podem ser
descomissionados — coordenar com o WP1 (kill do POS-HTMX legado) e a base `gestor/`.
Até lá, os dois coexistem; o HTMX alinhado serve de referência visual.

## 6. Aberto (decidir no kickoff com o Pablo)
- Reuso (a) monorepo vs (b) copiar.
- Endpoints fixos vs Actions no contrato de escrita.
- Porta dev do KDS (PDV=:3002; KDS=:3003?) + como o nav/deploy liga as superfícies.
