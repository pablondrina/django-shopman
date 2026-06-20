# Surface Convergence Plan — organizar a bagunça de telas

> Inventário + arquitetura-alvo + ordem de convergência das superfícies (UI) do
> Shopman. Nasce do diagnóstico do Pablo (2026-06-11): "o KDS parece atrelado a um
> esquema de telas antigo — o que precisamos fazer para organizar essa bagunça?".
> Constrói sobre os ADRs de superfície já aceitos:
> [adr-012](../decisions/adr-012-headless-surface-contract.md) (contrato headless
> Projection+Actions), [adr-013](../decisions/adr-013-pos-offline-policy-and-surface-ownership.md)
> (surface ownership), [adr-014](../decisions/adr-014-surface-data-presentation-cut.md)
> (corte dado↔presentation). Pilar-mãe: `project_excellence_refactor_initiative`
> (refazer TODAS as superfícies, 4 pilares) + `project_ui_apps_separation`.

## 1. Inventário real (o que existe hoje)

### Superfícies Nuxt (`surfaces/`)
| surface | arquivos .vue/.ts | estado | veredito |
|---|---|---|---|
| `pos-uithing-nuxt` | 98 | **VIVO** (PDV endurecido, redesign 2026-06) | **canônico** (adr-013) |
| `storefront-uithing-nuxt` | 256 | WIP grande, parado em 2026-06-05 | candidato a storefront-alvo |
| `storefront-nuxt` | 56 | experimento anterior, parado | provável arquivar |
| `backstage-nuxt` | 33 | scaffold, parado; `pos.vue` declarado histórico (adr-013) | provável arquivar |

### Superfícies Django (`shopman/`)
| superfície | stack | rota | estado |
|---|---|---|---|
| **storefront** | Django templates + HTMX | `/` | **VIVO** (a loja) |
| **gestor** (`backstage/templates/gestor/`, `runtime/`) | HTMX + Alpine + SSE | `/operacao/kds/...` | **VIVO** — KDS; "esquema antigo" |
| **POS-HTMX legado** (`backstage/templates/pos/`, `views/pos.py`) | HTMX | `/gestor/pos/...` | **MORTO-VIVO** — substituído pelo Nuxt POS (§5.1) |
| **admin_console** (`backstage/templates/admin_console/`) | Unfold (Django admin) | `/admin/operacao/...` | **VIVO** — Pedidos/Produção/Fechamento (WP8 canônico) |

## 2. Diagnóstico — a bagunça

1. **Três gerações de UI de operador coexistem:**
   - **Gen 1 — gestor-HTMX**: KDS (+ POS-HTMX legado), base `gestor/base.html`.
   - **Gen 2 — Unfold**: pedidos/produção/fechamento (admin_console, canônico WP8).
   - **Gen 3 — Nuxt/UI-Thing**: PDV (vivo). O KDS está preso na Gen 1.
2. **PDV duplicado:** o Nuxt POS substituiu o POS-HTMX legado, mas o legado **ainda
   existe** e o nav do gestor aponta pra ele (`backstage:pos`), não pro Nuxt.
3. **Storefront com 3 versões:** Django (vivo) + 2 Nuxt (storefront-nuxt 56,
   storefront-uithing-nuxt 256). Qual é o futuro? Indefinido.
4. **Experimentos Nuxt parados** (backstage-nuxt, storefront-nuxt) — meio-caminho,
   status ambíguo (adr-013 já marca o pos.vue do backstage-nuxt como histórico).

## 3. Princípio organizador — UM sistema canônico por superfície

Convergir + podar, **não acumular**. O alvo natural (já implícito nas decisões):

- **Nuxt/UI-Thing** para as superfícies **ricas/kiosk** (interação densa, tempo real,
  customer-facing): **PDV** ✅, **KDS**, **tela do cliente** (POS customer display +
  board de retirada), **storefront**.
- **Unfold** para o **CRUD de gestão** (back-office tabular: pedidos, produção,
  fechamento, catálogo, clientes) — onde o admin Django + Unfold canônico já é forte.
- Tudo sob o **contrato headless** (Projection + Actions, adr-012/014): a superfície
  renderiza intent, o orquestrador decide. Isso é o que torna trocar a camada de
  apresentação barato (foi assim que o PDV migrou).

> **Decisão FECHADA (Pablo, 2026-06-20) — o alvo do KDS é Nuxt/UI-Thing.** Unifica o
> design system de verdade (mesmo rail, tokens, componentes do PDV/loja; aposenta a base
> gestor-HTMX). Já existe um redesign Nuxt do KDS concluído (`surfaces/kds-uithing-nuxt`,
> commit `539b861a`) — o trabalho de apresentação está feito; falta ratificar o contrato
> headless e **matar o KDS-HTMX** (gestor/runtime), análogo ao kill do POS-HTMX. O
> polimento HTMX de hoje serve de referência visual e como fallback até o cutover.

## 4. Ordem de convergência (work packages)

### WP1 — Matar o POS-HTMX legado (§5.1) · ✅ CONCLUÍDO
> Feito (capítulos anteriores + revisão do backoffice 2026-06-20): `views/pos.py`,
> `templates/pos/` e as rotas `gestor/pos/*` já não existem; os `test_pos_*` já exercem
> o contrato headless/Nuxt (`api/v1/backstage/pos/`). Resíduo final (link morto "POS" no
> nav do admin) corrigido em `f175c6b6` — usa `SHOPMAN_POS_BASE_URL`, oculto se vazio.
> O blinding do caixa cego (§2.6) segue como item próprio se ainda houver consumo legado.

Remover a camada de **view HTMX** do POS legado (o Nuxt POS já a substituiu).
**Footprint exato:**
- `shopman/backstage/views/pos.py` (15 funções HTMX-view: `pos_view`,
  `pos_tabs`, `pos_tab_*`, `pos_cash_*`, `pos_shift_summary`, `pos_close`,
  `pos_cancel_last`, `pos_customer_lookup`, `pos_operator_*`).
- `shopman/backstage/views/__init__.py` — imports + `__all__` desses nomes.
- `shopman/backstage/urls.py` — 15 rotas `gestor/pos/*` (linhas ~40-55).
- `shopman/backstage/templates/pos/` (11 templates).
- `gestor/base.html` — link de nav "Ponto de Venda" (`backstage:pos`) → remover
  (o PDV vive como deploy Nuxt separado, não como rota Django) ou apontar ao Nuxt.

**⚠️ O custo real (não é delete de 5 min):** as views HTMX são o **harness de teste**
de **~12 `test_pos_*.py`** que cobrem comportamento **compartilhado** com o Nuxt
(fire, move_lines, discount_notes, customer_memory, d1_employee, intent_contract,
keyboard, layout, cancel, cash_register, shift_summary, tabs). Deletar as views
**órfã esses testes e perde cobertura** do backend que o Nuxt usa. **O kill limpo =
primeiro MIGRAR esses testes pra exercer a API Nuxt (`api/v1/backstage/pos/`),
confirmar cobertura equivalente, e SÓ ENTÃO deletar a camada de view.** Triar quais
já estão cobertos pelos testes de `backstage/api/operations.py` (evitar duplicar).

**Desbloqueio:** matar o legado completa o **caixa cego §2.6** — `cash_total_display`/
`digital_total_display` só seguem na projeção porque `pos/partials/shift_summary.html`
os consome; sem o legado, removem-se da projeção (blinding no payload, fecha a dívida).

### WP2 — Podar/arquivar experimentos Nuxt mortos
Decidir e executar: `storefront-nuxt` (56) vs `storefront-uithing-nuxt` (256) —
manter um como storefront-alvo, arquivar o outro; `backstage-nuxt` (33, pos.vue já
histórico por adr-013) — arquivar. Tira ambiguidade do repo. (Pablo não aprovou
ainda — pendente.)

### WP3 — KDS → Nuxt · ✅ DECIDIDO (Pablo, 2026-06-20); migração pendente
Alvo ratificado: **Nuxt** (§3). Já existe `surfaces/kds-uithing-nuxt` (redesign concluído,
`539b861a`) sobre o design system do PDV (rail, tokens, componentes). Falta: confirmar o
contrato headless (`api/v1/backstage/kds/`), migrar os testes que ainda dependem das views
gestor-HTMX, e **matar o KDS-HTMX** (`gestor/`/`runtime/` + rotas + nav) — análogo ao WP1.
O KDS-customer-board e a futura tela-do-cliente-do-PDV compartilham a base "customer display".

### WP4 — Storefront (pilar Loja Online) · ✅ CONVERGIDO + DEPLOYADO (2026-06-20)
O storefront-alvo é o **`storefront-uithing-nuxt`** (headless, consome `/api/v1/*`).
As páginas Django de cliente foram aposentadas (headless de verdade), a loja Nuxt
passou por redesign completo (tipografia/layout/cor/marca) + **auditoria reversa**
(Lotes 1-3) e está **no ar no staging**. O `storefront-nuxt` (56) e `backstage-nuxt`
(33) continuam candidatos a arquivar no WP2. Resta a **padronização de URLs pt-BR**
(ver `docs/plans/URL-STANDARDIZATION-PLAN.md`).

### WP5 — Gestor de Pedidos / back-office (Unfold) · ✅ AUDITADO (2026-06)
admin_console Unfold canônico revisado na BACKOFFICE-UNFOLD-REVISION (3 camadas,
mergeada + deployada). É a casa do CRUD de gestão; nada estrutural pendente.

## 5. Estado atual desta iniciativa (2026-06-20)
- **Feito:** PDV redesenhado (Nuxt); **storefront convergido p/ Nuxt + auditado + deployado
  (WP4)**; **WP1 kill POS-HTMX legado** concluído; backoffice Unfold auditado (WP5).
- **Próxima execução (em ordem):**
  1. **WP3 — KDS → Nuxt** (decidido): ratificar contrato `api/v1/backstage/kds/`, migrar
     testes que dependem das views gestor-HTMX, **matar o KDS-HTMX** (`gestor/`/`runtime/`
     + rotas + nav). O redesign Nuxt já existe (`kds-uithing-nuxt`, `539b861a`).
  2. **WP2 — podar experimentos Nuxt mortos** (`storefront-nuxt`, `backstage-nuxt`) →
     arquivar; tira ambiguidade do repo. (Barato; pode ir junto com o WP3.)
  3. **Padronização de URLs pt-BR** (storefront) — `docs/plans/URL-STANDARDIZATION-PLAN.md`.
- **Depois (novas frentes, fora de convergência):** tela-do-cliente do PDV (customer
  display, base compartilhada com o KDS-board); produção first-class; pilar Agentic.
