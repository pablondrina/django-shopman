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

> **Decisão ABERTA (precisa do Pablo) — o alvo do KDS:** migrar pro Nuxt/UI-Thing
> (unifica o design system de verdade — mesmo rail, tokens, componentes; aposenta a
> base gestor-HTMX) **ou** manter HTMX (acabou de ser alinhado ao PDV visualmente) e
> só organizar o entorno. **Recomendação:** migrar pro Nuxt no médio prazo (é o
> Excellence Refactor; o KDS é rico/tempo-real, encaixa no molde do PDV; o polimento
> HTMX de hoje vira a referência visual). Curto prazo: o KDS HTMX alinhado serve.

## 4. Ordem de convergência (work packages)

### WP1 — Matar o POS-HTMX legado (§5.1) · APROVADO, mas é work-package
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

### WP3 — Decidir o alvo do KDS (§3) e, se Nuxt, migrar
Ratificar Nuxt vs HTMX. Se Nuxt: nasce `surfaces/kds-*` sobre o mesmo contrato
headless + design system do PDV (rail, tokens, componentes compartilháveis). O
KDS-customer-board (display de retirada) e a futura tela-do-cliente-do-PDV podem
compartilhar a base "customer display".

### WP4 — Storefront (pilar Loja Online)
Convergir o storefront (Django vivo → Nuxt-alvo escolhido no WP2), mobile-first,
branding pleno. Pilar grande, próprio.

### WP5 — Gestor de Pedidos / back-office (Unfold)
Auditar o admin_console (Unfold canônico) — aderência ao tema/componentes; é a casa
do CRUD de gestão. Provável já bom (WP8 Arc F); confirmar.

## 5. Estado atual desta iniciativa
- **Feito (2026-06):** PDV redesenhado (Nuxt) + KDS/gestor **neutralizado e alinhado
  visualmente ao PDV** (paleta, rounded-md, tema light-first, rail dark-spine).
- **Próximo:** ratificar §3 (alvo KDS) + executar WP1 (kill legado, com migração de
  testes) — ambos dependem de decisão/scheduling do Pablo.
