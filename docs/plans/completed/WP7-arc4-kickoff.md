# WP7 · Arc 4 — move_lines (§2.3) + fire-to-kitchen progressivo (§2.5) · kickoff autossuficiente

> Prompt de abertura para sessão limpa. Branch `redesign/surface-excellence`.
> **Arcs 1–3 estão FECHADOS.** O seam dado/contrato (Arc 1), as 3 telas-núcleo + a camada
> `app/presentation/` TS (Arc 2) e a tela de Pagamento Odoo + manager-PIN por-permissão + caixa cego
> (Arc 3) estão entregues e verificados ao vivo. Agora: **mover linhas entre comandas** (split/transfer/
> merge, preço congelado) e **disparo progressivo de cozinha** (fire/unfire por linha, `fired_lines`),
> recompostos sobre a Presentation com o mesmo rigor dos arcos anteriores.

## Postura & autonomia
**AUTONOMIA TOTAL** (Pablo, 2026-06-06): decidir por mérito e prosseguir sem perguntar.
**NUNCA menor-diff/menor-esforço** — só a solução mais Simples/Robusta/Elegante pelo mérito
(`feedback_never_recommend_smallest_diff`). Zero gambiarra, zero residual em renames/deleções, **não
inventar features**. Verde a cada passo; commit coerente por incremento. Acessibilidade + omotenashi são
first-class (`feedback_accessibility_omotenashi_first_class`): alvos grandes, estado de cozinha
inequívoco, idoso em mente — o balcão é ambiente de pressão.

**Core SAGRADO** (`packages/`, intocável sem autorização explícita). `shop/` é orquestrador editável mas
**cada mudança sinalizada**. Antes de "o Core/orquestrador não cobre", assumir que cobre e procurar onde
(`feedback_respect_core_no_reinvent`). **O write-side de move/fire JÁ EXISTE e é robusto** — este arco
**reusa, não reinventa** (ver Estado atual). **Zero política no cliente:** quais linhas movíveis, o que
já foi disparado, preço congelado — tudo vem da Projection/payload; a tela **renderiza**.

## ⚠️ Nomenclatura (travada)
Comanda = `Tab`/`POSTab` (NUNCA "Command"). Ver `feedback_comanda_is_tab_not_command`. "Disparar"/
"Enviar para cozinha" = **fire** (o ato auditável anti-fraude — comida sem pagamento). `move_lines`
**congela preço** (não re-precifica). Ver `feedback_production_vs_sales` (KDS Prep = montagem do pedido,
NUNCA WorkOrder de pedido).

## Ler primeiro (obrigatório, antes de editar)
- `docs/redesign/05-spec-pos.md` **§2.3 (Comanda/mesas — move_lines), §2.5 (Fire-to-kitchen), §2.2
  (multi-select de linhas — Shopify v11), §1.3 (fire-to-kitchen progressivo + fulfillment_type)** — a spec.
- `docs/decisions/adr-014-surface-data-presentation-cut.md` — o contrato Projection(dado)/`Action`/
  Presentation(aparência). A Presentation do PDV é TS no Nuxt (`app/presentation/`).
- `project_wp7_pos_status` (estado consolidado + os 2 gotchas Nuxt abaixo) +
  `project_pos_visual_fidelity_deep_dive` (veredito ANTI-FRAUDE do disparo — **ler com atenção**: a
  matriz de quando comida vai à cozinha, dedup por `fired_line_ids_for_session`, e o risco residual
  parqueado) + `project_pos_uithing_redesign_goal` (benchmarks: STORES roteia por estação; Shopify
  multi-select).

## Estado atual (auditado 2026-06-06 — não re-descobrir)
- **Write-side robusto e PRONTO em `usePosSale.ts` (reusar):**
  - `openMoveDialog()` — persiste+recarrega a comanda (as linhas precisam dos `line_id` do servidor) e
    abre o diálogo. `submitMove({mode, lineIds, toTabRef?, toSessionKey?, closeSource?})` — split/
    transfer/merge via `move_lines` (preço congelado no Core).
  - `fireTab()` — persiste o on-screen e dispara o **delta não-disparado** (fire progressivo; nunca
    duplica — dedup por `fired_line_ids_for_session` no Core). `unfireTab(lineId)` — cancela o envio de
    UMA linha (`line_ids`).
  - `canFireTab` (capability `kitchen_handoff.fire_action_ref`), `canRenameTab`, `firing`/`saving` flags.
- **Componentes a recompor (têm lógica inline a drenar p/ Presentation):**
  - `app/components/PosMoveLinesDialog.vue` (145 ln) — modos split/transfer/merge, seleção de linhas
    (Set), `canSubmit`, `suggestedSplitRef`, lista de comandas-destino. **Lógica de seleção/validação/
    shaping mora inline** → drenar p/ `app/presentation/moveLines.ts` (puro, testado): quais linhas
    selecionáveis, shape do payload por modo, regra de habilitar submit por modo, nota de preço-congelado.
  - `app/components/PosCartPanel.vue` (563 ln) — afford. de fire/unfire por linha (350-377) + botão
    "Enviar para cozinha (N)" / "Tudo na cozinha" (434-439) usando `unfiredCount`. Estado `fired` por
    linha já vem em `POSCartItem.fired` + `line_id`. **Drenar o shaping do estado de cozinha** (fired vs
    firável, contagem, rótulo do botão, affordance fire/unfire) p/ `app/presentation/kitchen.ts` (puro,
    testado). Avaliar componente focado `PosKitchenFireBar`/per-line badge sobre o módulo.
- **Contrato (byte-estável, Arc 1):** `fire_tab`/`unfire_tab` Actions na Projection
  (`backstage/projections/pos.py`: kitchen_handoff capability; `fired` por linha computado de
  `Session.data["fired_lines"]` em `_tab_payload`/`build_open_tab`). `move_lines` via
  `backstage/api/operations.py`. **Não tocar backend** salvo necessidade comprovada (e então sinalizar +
  rodar pytest + regenerar `posContract.ts` se mexer no intent/schema).

## O trabalho do Arc 4
1. **move_lines §2.3** (`PosMoveLinesDialog` → limpo sobre a Presentation): nasce
   `app/presentation/moveLines.ts` (puro, testado) com o shaping hoje inline (seleção de linhas, shape
   por modo split/transfer/merge, gate de submit, nota de preço-congelado, sugestão de ref de split). O
   diálogo vira casca que consome o módulo. Reusar `submitMove`/`openMoveDialog` (write-side intacto).
   **Confirmação via `Action`** (não inventar CTA).
2. **fire-to-kitchen progressivo §2.5** (afford. de cozinha → limpo sobre a Presentation): nasce
   `app/presentation/kitchen.ts` (puro, testado): firável vs `fired`, contagem não-disparada, rótulo do
   botão (config-driven via `kitchen_handoff`), affordance fire/unfire por linha (via `presentation/
   actions`). Estado visual **inequívoco** do que já foi pra cozinha (o veredito anti-fraude exige
   clareza). Reusar `fireTab`/`unfireTab`. **Fire é o ato nomeado/auditável** — não diluir num genérico.
3. **multi-select de linhas §2.2 (avaliar por mérito):** Shopify v11 permite aplicar desconto/remoção/
   **fire** a várias linhas (Actions com `payload` multi-ref). Forte pra balcão. **Verificar se o
   backend já aceita `line_ids` em lote** (unfire já aceita `line_ids[]`); se sim e for limpo, expor a
   seleção múltipla na Presentation. **NÃO inventar** endpoint novo — se o lote não existir no contrato,
   parquear p/ shell (Arc 5) e anotar. Decidir por mérito após checar o contrato real.
4. **Ordem sugerida (incremento verde por peça):** move_lines → fire progressivo → (multi-select se o
   contrato cobrir). Commit coerente por peça.

## Decisões abertas (decidir por mérito)
- **Per-line fire vs delta-fire:** hoje `fireTab` dispara o delta não-disparado (tudo de uma vez);
  `unfire` é por-linha. §2.5 fala "enviar linhas". Avaliar se expor seleção de linhas para fire (lote) ou
  manter delta-fire + unfire por-linha (já cobre o fluxo). Checar o contrato (`fire_tab` aceita
  `line_ids`?) antes de decidir — **não inventar** se o backend só dispara o delta.
- **Roteamento por estação (STORES):** o KDS já roteia por receita/coleção/estação no backend; isso é
  read-side do KDS, **não** do PDV — fora do escopo Arc 4 (é tela KDS, ver WP8/spec backoffice).
- **D2/D3 (layout/impressão) = shell, Arc 5** — não travar aqui.

## Gates (verde ao fim de cada peça)
- `cd surfaces/pos-uithing-nuxt && export PATH="/opt/homebrew/bin:$PATH"` → `npx nuxi typecheck`
  (ignorar **pré-existentes** conhecidos: `djangoProxy.ts` `pair possibly undefined` + `nuxt.config.ts`
  `process` — `noUnusedLocals` está OFF) + `npx vitest run` (**baseline 48**; somar testes de
  `presentation/moveLines`+`kitchen`).
- Se tocar backend (projection/serializer/endpoint): `pytest shopman/shop/tests shopman/backstage/tests -q`
  (e `storefront/tests` se cruzar a fronteira). **NÃO** `make test-framework`
  (`project_backstage_pos_test_pollution`). `make admin` só se tocar Admin/Unfold. Se mexer no intent/
  schema: regenerar `posContract.ts` via `manage.py export_pos_schema` e checar o drift-test.

## Preview ao vivo (prova obrigatória, `preview_*`) — receita validada no Arc 3
- Servers em `.claude/launch.json`: **django** (8000) + **pos** (3002). `preview_start` em cada. Browser
  via **`http://127.0.0.1:3002/`** (gotcha IPv6 426 em `localhost`).
- **Autenticar sem digitar credencial** (proibido): semear sessão server-side via `manage.py shell`
  (`SessionStore` + `_auth_user_id`/`_auth_user_backend`/`_auth_user_hash` + `pos_active_operator =
  operator_card(u)`; `s.create()`; print `session_key`) e injetar `document.cookie="sessionid=<key>;
  path=/"` + navegar. **Auto-lock atrapalha:** `POSTerminal.default().metadata['auto_lock_seconds']=0`
  (RESTAURAR removendo a chave ao fim — não deixar resíduo no db dev). Seed tem comandas com itens
  (#1007, #1011, #1012) e uma "não pago" (#1012, já disparada) — bons casos p/ move/fire.
- **Após rename/delete de componente, reiniciar o dev server pos** (`preview_stop`+`preview_start`) p/
  limpar erros HMR stale do grafo Vite (custou ruído no Arc 3). Screenshot de cada tela; console
  `level=error` limpo; `preview_network` p/ os POSTs de move/fire.

### ⚠️ 2 gotchas Nuxt (não repetir)
1. **`usePosTerminal` usa `useFetch`, não `useAsyncData`+`$fetch`** (só useFetch transfere o payload SSR;
   com useAsyncData o cliente re-semeia o lock com `operator=null` → trava por hidratação).
2. **Composable `.ts` chamado depois do `await` do shell NÃO pode chamar composable Nuxt** (useCookie/
   useRuntimeConfig/usePosApiPath/usePosAction) — o contexto de instância não sobrevive ao await. Padrão:
   o shell cria as primitivas Nuxt e passa como **deps**; o composable usa só primitivas vue + utils
   puros. Lifecycle hooks (onMounted) ficam no shell.

## Ao terminar
Commit coerente por peça; atualizar `project_wp7_pos_status` (Arc 4 progresso/done) + a linha em
`MEMORY.md`. Seguir para **Arc 5** (shell visual: D2 layout cart-dir×ticket-esq + D3 impressão Ubuntu +
fidelidade benchmark + multi-select/rail-de-funções/tiles-de-ação se parqueados).
```bash
cd surfaces/pos-uithing-nuxt && export PATH="/opt/homebrew/bin:$PATH" && npx nuxi typecheck && npx vitest run
```
