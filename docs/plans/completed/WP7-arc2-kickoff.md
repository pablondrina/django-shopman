# WP7 · Arc 2 — Presentation TS + telas-núcleo do PDV · kickoff autossuficiente

> Prompt de abertura para sessão limpa. Branch `redesign/surface-excellence`.
> **Arc 1 do WP7 está FECHADO** (seam de dado & contrato): S4 drain (CQRS-puro) + B (schema POS
> compartilhado) + C (E3/E4 — labels→OmotenashiCopy, cores→tone) + S7-parcial (R-A/R-B/R-C/R-D no
> test_import_boundaries). Agora é a **camada de apresentação** do PDV em Nuxt/TS.

## Postura & autonomia
**AUTONOMIA TOTAL** (Pablo, 2026-06-06): decidir por mérito e prosseguir sem perguntar.
**NUNCA menor-diff/menor-esforço** — só a solução mais Simples/Robusta/Elegante pelo mérito
(`feedback_never_recommend_smallest_diff`). Zero gambiarra, zero residual em renames/deleções, **não
inventar features** (notify-me/ACP/WhatsApp-in-chat = WP9, não pré-emptar). Verde a cada passo; commit
coerente por incremento de tela.

**Core SAGRADO** (`packages/`, intocável sem autorização explícita — exceto `move_lines`, que é Arc 4,
não agora). `shop/` é orquestrador editável mas **cada mudança sinalizada**. Antes de "o Core/orquestrador
não cobre", assumir que cobre e procurar onde (`feedback_respect_core_no_reinvent`). **Zero política no
cliente:** preço/disponibilidade/gates/CTA vêm da `Projection`+`Action[]` do orquestrador.

## ⚠️ Nomenclatura (travada — não repetir o erro)
**Comanda (pt-br) = `Tab` / `POSTab` em inglês. NUNCA "Command"/"Command Board"** (tradução errada; não
existe no código). O termo canônico é `POSTab`/`pos_tab` (Python **e** Nuxt). Ver
`feedback_comanda_is_tab_not_command`. As **3 telas-núcleo** deste arco:
- **Operator Lock** — spec §2.1 (entrada/PIN; `PosLockScreen` já existe).
- **Sale Workspace** — spec §2.2 (Venda / Smart Grid: grade + ticket/comanda + numpad — o coração).
- **Tab Board** — spec §2.3 ("Comanda / mesas": mapa de comandas abertas, seleção/destino; `move_lines`
  é Arc 4, aqui só listar/selecionar/abrir).

## Ler primeiro (obrigatório, antes de editar)
- `docs/redesign/05-spec-pos.md` **§1 (tenets) + §2 (telas e o contrato que cada uma consome)** — a spec.
- `docs/redesign/04-architecture.md` §4 + `docs/decisions/adr-014-surface-data-presentation-cut.md` — o
  contrato **`Projection`(dado) / `Action` / `Presentation`(aparência)**. A `Presentation` do PDV é
  **TypeScript no Nuxt**, dando shape de tela à `Projection` serializada (a mesma que storefront/admin
  consomem).
- `project_pos_uithing_redesign_goal` (benchmarks Shopify/STORES/Take.app/Odoo; modelagem comanda/PIN) +
  `project_pos_visual_fidelity_deep_dive` (feedback de aparência — vale no shell, Arc 5) +
  `project_wp7_pos_status` (Arc 1 done; contrato consolidado) + `project_excellence_refactor_initiative`.
- `project_pos_staging_deploy` + `project_backstage_pos_test_pollution` (**NÃO** `make test-framework`).

## Estado atual (auditado 2026-06-06 — não re-descobrir)
- **REST que alimenta o Nuxt:** `backstage/api/operations.py::POSView.get` devolve
  `{"pos","shift","tabs"}` via `projection_data(<dataclass>)` (serializa a Projection RAW). Comandos POS
  via as views REST de `backstage/api/operations.py` + `backstage/urls.py` (`gestor/pos/...`). Contrato
  byte-estável (Arc 1 fechou E3/E4 + schema gerado).
- **Reusar (OURO — a spec manda preservar; NÃO reescrever):**
  - Transporte/contrato: `server/utils/djangoProxy.ts` (CSRF handshake), `app/utils/posIntent.ts`,
    `app/types/pos.ts`, `app/generated/posContract.ts` (gerado por `manage.py export_pos_schema`;
    drift-test `shop/tests/test_pos_schema_export.py`), `app/utils/operatorAccess.ts`,
    `app/utils/operatorLock.ts`, `app/utils/posTabLifecycle.ts`, `app/composables/*`.
  - Componentes já first-class: `PosLockScreen`, `PosPinPad`, `PosNumpad`, `PosProductTile`,
    `PosCartPanel`, `PosTabPickerDialog`, `PosCheckoutWorkspace`, `PosCashPanel`, `PosMoveLinesDialog`,
    `PosTerminalHealth`, `PosAddressAutocomplete` — **pescar os bons**, recompor limpo.
- **`app/app.vue` é o "frankenstein"** que o Pablo rejeitou (orquestração monolítica, política no
  cliente). **NÃO copiar.** Reconstruir a composição limpa per spec.
- **NÃO existe `app/presentation/` ainda** — **este arco a cria.**

## O trabalho do Arc 2
1. **Nasce `surfaces/pos-uithing-nuxt/app/presentation/`** (camada Presentation TS): funções/composables
   puros que recebem a `Projection` serializada (tipada por `types/pos.ts`/`posContract.ts`) e devolvem
   o **shape de tela** (labels já vêm prontos do serializer pós-E3/E4; numpad→qtd, agrupamentos, estado
   de tile, mapeamento de `Action`→affordance). **Zero política, zero aritmética de preço/disp.**
2. **Recompor as 3 telas** consumindo `Projection`+`Action[]` via proxy+contrato, **sem** a orquestração
   frankenstein do `app.vue`. Roteamento por `pages/` (Nuxt) se fizer sentido por mérito (hoje é
   app.vue monolito — avaliar nascer `pages/`). Cada `Action` aciona via o composable de comando
   existente (`usePosAction`), idempotente; a tela **não inventa** CTA nem resolve gate.
3. **Ordem sugerida (incremento verde por tela):** Operator Lock → Sale Workspace → Tab Board. Commit
   coerente por tela.

## Decisões abertas (decidir por mérito)
- **`pages/`-routing vs shell único** no Nuxt: por mérito; o app.vue monolito sai.
- **D2 (layout cart-dir Shopify × ticket-esq Odoo) e D3 (impressão)** = shell visual, **Arc 5** — não
  travar aqui. Aqui é estrutura/contrato de tela, não fidelidade pixel.

## Gates (verde ao fim de cada tela)
- `cd surfaces/pos-uithing-nuxt && export PATH="/opt/homebrew/bin:$PATH"` → `npx nuxi typecheck`
  (ignorar erros **pré-existentes** conhecidos em `djangoProxy.ts`/`nuxt.config.ts`) + `npx vitest run`.
- Se tocar backend (projection/serializer/endpoint): `pytest shopman/shop/tests shopman/backstage/tests -q`
  (e `storefront/tests` se cruzar a fronteira). **NÃO** `make test-framework`. `make admin` só se tocar
  Admin/Unfold.
- **Preview ao vivo (prova obrigatória, `preview_*`):** Django :8000 (admin/admin) + Nuxt :3002 via
  **127.0.0.1** (gotcha IPv6 426), PIN operador **1234** (auto-lock 60s atrapalha). Screenshot de cada
  tela tocada. Verificar console/network sem erro.

## Ao terminar
Commit coerente por tela; atualizar `project_wp7_pos_status` (Arc 2 progresso/done). Seguir para **Arc 3**
(Checkout/pagamento estilo Odoo + manager-PIN por-permissão + caixa cego) conforme `WP7-pos-kickoff.md`.
```bash
cd surfaces/pos-uithing-nuxt && export PATH="/opt/homebrew/bin:$PATH" && npx nuxi typecheck && npx vitest run
```
