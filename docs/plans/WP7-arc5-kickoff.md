# WP7 · Arc 5 — Shell visual: D2 layout + D3 impressão + fidelidade benchmark + parqueados · kickoff autossuficiente

> Prompt de abertura para sessão limpa. Branch `redesign/surface-excellence`.
> **Arcs 1–4 estão FECHADOS.** O seam dado/contrato (Arc 1), a camada `app/presentation/` TS + as 3
> telas-núcleo (Arc 2), o Pagamento Odoo + manager-PIN + caixa cego (Arc 3) e o move_lines +
> fire-to-kitchen progressivo (Arc 4) estão entregues e verificados ao vivo. **A política, o dado e a
> apresentação-como-shaping estão prontos e testados.** Arc 5 é a **fase de shell visual**: a
> *aparência*, o *layout*, a *fidelidade ao benchmark*, a *impressão* e as *interações parqueadas* — a
> última camada da ordem inegociável dado→contrato→apresentação→**shell**.

## ⚠️ Postura desta fase — visual é iterativo COM o Pablo (NÃO autônomo cego)
Os arcos 1–4 tiveram **autonomia total** porque eram dado/contrato/lógica (verificáveis por teste e por
mérito). **Arc 5 é diferente:** é gosto, muscle-memory de balcão e fidelidade a benchmarks que o Pablo
conhece tela-a-tela. A lição das rodadas de fidelidade anteriores (`project_pos_visual_fidelity_deep_dive`)
é clara: **cadência visual/iterativa — propor → mostrar preview → aprovar → próxima zona.** Não despejar
um redesign monolítico. Decidir por mérito o que é técnico (tokens, alturas, overflow, a11y), **mas
SURFACEAR ao Pablo** o que é preferência de layout/feel antes de cravar. Em especial **D2 (lado do
carrinho) NÃO é decisão de mérito** — é muscle-memory da equipe Nelson (ver Decisões abertas).
**NUNCA menor-diff/menor-esforço** (`feedback_never_recommend_smallest_diff`); zero gambiarra; não
inventar features. **Acessibilidade + omotenashi first-class** (`feedback_accessibility_omotenashi_first_class`):
alvos grandes, contraste alto, idoso em mente, copy acolhedor — o balcão é ambiente de pressão.

**Core SAGRADO** (`packages/`). `shop/` editável mas **cada mudança sinalizada**. **Esta fase é
quase-toda Nuxt/CSS** — idealmente **zero backend** (o contrato está pronto; a tela só renderiza melhor).
Se precisar de um dado novo da Projection, é sinal de que talvez esteja inventando — reler o contrato
primeiro (`feedback_respect_core_no_reinvent`). **Zero política/copy hardcoded nova:** labels vêm de
`Action`/OmotenashiCopy, cores de design-tokens, presets do contrato (ver `feedback_tailwind_only_existing_classes`
+ `feedback_icon_size_convention`).

## ⚠️ Nomenclatura (travada)
Comanda = `Tab`/`POSTab` (NUNCA "Command"); tela do mapa = **Tab Board** (`feedback_comanda_is_tab_not_command`).
"Disparar"/"Enviar para cozinha" = **fire** (ato auditável anti-fraude). Personas sempre
Offerman/Stockman/... (`feedback_persona_names_only`). Django `{# #}` é single-line só
(`feedback_django_comments_single_line`) — mas o PDV é Nuxt/Vue, então o cuidado é com `<!-- -->`/JSX-less.

## Ler primeiro (obrigatório, antes de editar)
- `docs/redesign/05-spec-pos.md` **§1 (tenets — ergonomia de balcão, 1-2 toques), §2.2 (Smart Grid:
  tiles-de-ação + rail de funções + multi-select), §6 (decisões adiadas D2/D3 + parqueados)** — a spec.
  > Cabeçalho da spec: *"layout (D2) e impressão (D3) são fase de shell, não desta spec"* — **é AGORA.**
- `docs/redesign/02-confronto.md` **§D2 (cart-direita Shopify vs ticket-esquerda Odoo/nosso) e §D3
  (web/Nuxt mantido; impressão Ubuntu viável: kiosk-printing / WebSerial+ESC-POS / ePOS-Print de rede).**
- `docs/decisions/adr-014-surface-data-presentation-cut.md` — o contrato Projection/`Action`/Presentation.
  **A regra de ouro do shell:** mude APENAS aparência/layout; jamais reintroduza política/cálculo/copy no
  cliente. O que `app/presentation/*.ts` já shapeia continua sendo a fonte; o shell só **dispõe** melhor.
- **Benchmarks (ordem do Pablo, 2026-06-04):** `docs/research/pos-benchmarks/` → `shopify.md` (Smart Grid,
  cart-à-direita, single-continuous-flow, "staff-experience-first"), `stores.md` (ecossistema unificado,
  roteamento por estação), `take-app.md` (WhatsApp-first), `synthesis.md`. **1. Shopify POS** (fluidez/
  Smart Grid) **2. STORES** **3. Take.app** **4. Odoo** (último). Ver `project_pos_uithing_redesign_goal`.
- `project_pos_visual_fidelity_deep_dive` (**ler com atenção** — os 6 feedbacks duros do Pablo sobre
  aparência/organização/fluidez; muitos já endereçados em PRs antigos, mas REAVALIAR na era Presentation:
  sobreposição cart/grade, navegação difusa entre telas, cards de comanda altura-fixa, tile de produto,
  checkout-não-formulário) + `project_wp7_pos_status` (estado consolidado + os 2 gotchas Nuxt).

## Estado atual (auditado 2026-06-06 — não re-descobrir)
- **Shell:** `app/app.vue` é casca fina (515 ln pós-Arc-2): primitivas Nuxt + terminal/lock + atalhos de
  teclado (F2 board / F3 busca / F4 checkout / Esc volta), passa tudo p/ `usePosSale`. As telas
  (`PosTabBoard` / `PosProductGrid` + `PosProductTile` / `PosCartPanel` / `PosPaymentWorkspace` /
  `PosCashPanel` / `PosMoveLinesDialog` / `PosTabPickerDialog`) consomem `app/presentation/*.ts`
  (actions, catalog, tabBoard, numpad, payment, cash, **moveLines**, **kitchen**) — funções puras testadas.
- **Layout atual (D2 = nosso/Odoo, ticket-à-esquerda):** sale view é
  `md:grid-cols-[340px_minmax(0,1fr)]` com `<aside>` (PosCartPanel) em `md:order-1` (ESQUERDA) e
  `PosProductGrid` à direita. Shell de viewport fixo a partir de `md` (`md:h-[100dvh] md:overflow-hidden`),
  cada coluna com scroll interno; mobile (<md) rola a página de propósito (POS = ferramenta de tablet/
  balcão). **Trocar p/ cart-à-direita (Shopify) é só CSS** (3 camadas) — mas é decisão de muscle-memory.
- **Componentes UI Thing:** ~9 copiados + Sheet + Sonner. Ausentes a avaliar (catálogo `npx ui-thing add`,
  95 componentes): NumberField, Tabs, ScrollArea, ToggleGroup, Skeleton, Avatar, Splitter, Command.
  **Regra:** componente canônico > classes copiadas (espelha a disciplina Unfold do backoffice, mas aqui é
  UI Thing). `feedback_no_external_component_lib`: manter custom Alpine+HTMX no storefront; **no PDV é
  Nuxt+Vue+UI-Thing** (a stack já escolhida desta superfície) — UI Thing é o vocabulário canônico daqui.
- **Impressão (D3):** **ainda não existe** caminho de impressão no PDV Nuxt. É prototipagem nova desta fase.

## O trabalho do Arc 5 (incremento verde + preview por zona, cadência com o Pablo)
> Ordem sugerida; cada peça = 1 commit coerente + 1 preview mostrado ao Pablo antes da próxima.

1. **Linguagem de layout única (fidelidade) — a zona mais importante.** Reavaliar header/regiões/
   espaçamento/tipografia/alturas/overflow consistentes entre Tab Board, Sale, Pagamento, Caixa, Lock —
   o feedback nº2 do Pablo ("cada tela é uma coisa"). Tokens existentes, sem classes órfãs. Alturas
   uniformes (cards de comanda, tiles de produto). Mirar **fluidez Shopify / hiper-foco Odoo** sem
   regressão de capacidade. **Propor → preview → aprovar por tela.**
2. **D2 — lado do carrinho (DECIDIR COM O PABLO, não sozinho).** Apresentar o trade-off (Shopify
   cart-direita = padrão moderno / muscle-memory atual = ticket-esquerda Odoo) e **perguntar** antes de
   flipar. Implementação é trivial (ordem do grid) — o custo é re-treinar a mão da equipe Nelson.
3. **Parqueados §2.2 (avaliar feel no shell, contrato já cobre):**
   - **Multi-select de linhas** — o backend **aceita `line_ids[]` em fire e unfire** (verificado no Arc 4).
     Expor seleção múltipla na Sale view (checkboxes/long-press estilo Shopify v11) p/ **fire/unfire/
     desconto/remoção em lote** via os `Action`s. `usePosSale.fireTab` hoje dispara o delta; estender p/
     aceitar `lineIds` opcional (o endpoint já aceita) — **sem inventar endpoint**. Shaping novo →
     `app/presentation/` (puro, testado), seleção como estado de tela.
   - **Rail vertical de funções** (Shopify): lock/caixa/conectividade/board a 1 toque.
   - **Tiles-de-ação-na-grade** (Smart Grid): venda avulsa/desconto como tiles na grade.
   Cada um: avaliar feel, propor ao Pablo, só então construir. **NÃO** empilhar todos de uma vez.
4. **D3 — impressão Ubuntu (PROTOTIPAR).** Recibo/comanda de cozinha. Avaliar kiosk-printing (Chrome
   `window.print` + CSS `@media print` / kiosk flags) vs WebSerial+ESC-POS vs ePOS-Print de rede. Começar
   pelo caminho web mais simples e robusto (CSS print de um layout de recibo), prototipar e **flagar p/
   validação em hardware real** (`project_infra_wps_need_docker_validation`: o que não dá p/ verificar em
   sandbox, implementa + sinaliza critério end-to-end pro reviewer local com impressora).
5. **Customer-facing display** (brand idle/checkout) — **futuro, fora do Arc 5** salvo pedido do Pablo.

## Decisões abertas (SURFACEAR ao Pablo — não cravar por mérito)
- **D2 (lado do carrinho):** muscle-memory Nelson. **Perguntar.**
- **Quanto redesenhar:** a fidelidade é "reskin/reorganização, não reescrita de lógica"
  (`project_pos_visual_fidelity_deep_dive`). Confirmar o apetite (refino incremental vs linguagem nova).
- **Quais parqueados valem o balcão:** multi-select é forte (Shopify); rail/tiles avaliar feel. Pablo decide.
- **D3 alvo de hardware:** qual impressora/protocolo a Nelson usa no Ubuntu (define WebSerial vs rede vs kiosk).

## Gates (verde ao fim de cada peça)
- `cd surfaces/pos-uithing-nuxt && export PATH="/opt/homebrew/bin:$PATH"` → `npx nuxi typecheck`
  (ignorar **pré-existentes** conhecidos: `djangoProxy.ts` `pair possibly undefined` + `nuxt.config.ts`
  `process`) + `npx vitest run` (**baseline 59**; somar testes de qualquer `presentation/*` novo — ex.
  multi-select shaping). **Visual não tem teste** → a prova é **preview ao vivo + screenshot ao Pablo.**
- Se (improvável) tocar backend: `pytest shopman/shop/tests shopman/backstage/tests -q` (NÃO
  `make test-framework` — `project_backstage_pos_test_pollution`). Se mexer no intent/schema: regenerar
  `posContract.ts` via `manage.py export_pos_schema` + checar o drift-test. `make admin` só se tocar Admin.

## Preview ao vivo (prova obrigatória, `preview_*`) — receita validada nos Arcs 3-4
- Servers em `.claude/launch.json`: **django** (8000, venv python) + **pos** (3002, node /opt/homebrew/bin).
  `preview_start` em cada. Browser via **`http://127.0.0.1:3002/`** (gotcha IPv6 426 em `localhost`).
- **Autenticar sem digitar credencial** (proibido): semear sessão server-side via `manage.py shell`
  (`SessionStore` + `_auth_user_id`/`_auth_user_backend`/`_auth_user_hash` via `u.get_session_auth_hash()`
  + `pos_active_operator = operator_card(u)` [importável de `shopman.shop.services.pos`]; `s.create()`;
  print `session_key`) e injetar `document.cookie="sessionid=<key>; path=/"` **na origem 127.0.0.1** +
  reload. **Auto-lock atrapalha:** `POSTerminal.default().metadata['auto_lock_seconds']=0` —
  **RESTAURAR removendo a chave ao fim** (`md.pop('auto_lock_seconds'); save`) — zero resíduo no db dev.
  Seed tem comandas com itens (#1007, #1011, #1012-não-pago) — bons casos. Operador `admin`, PIN 1234.
- **Após rename/delete de componente, reiniciar o dev server pos** (`preview_stop`+`preview_start`) p/
  limpar HMR stale do grafo Vite. Screenshot de cada zona; console `level=error` limpo; `preview_network`
  p/ POSTs. **Mostrar screenshot ao Pablo e aguardar aprovação antes da próxima zona.**

### ⚠️ 2 gotchas Nuxt (não repetir)
1. **`usePosTerminal` usa `useFetch`, não `useAsyncData`+`$fetch`** (só useFetch transfere o payload SSR;
   useAsyncData re-semeia o lock com `operator=null` → trava por hidratação).
2. **Composable `.ts` chamado depois do `await` do shell NÃO pode chamar composable Nuxt** (useCookie/
   useRuntimeConfig/usePosApiPath/usePosAction) — contexto de instância não sobrevive ao await. Padrão: o
   shell (`<script setup>`) cria as primitivas Nuxt e passa como **deps**; o composable usa só primitivas
   vue + utils puros. Lifecycle hooks (onMounted) ficam no shell. (resolveAffordance e os `presentation/*`
   são imports estáticos puros — OK em qualquer lugar.)

## Ao terminar
Commit coerente por zona; atualizar `project_wp7_pos_status` (Arc 5 progresso/done) +
`project_pos_visual_fidelity_deep_dive` (o que da lista de feedback foi fechado na era Presentation) + a
linha em `MEMORY.md`. **Arc 5 fecha o WP7 PDV** — ao final, o pilar Ponto de Venda da
`project_excellence_refactor_initiative` está completo (dado→contrato→apresentação→shell). Follow-ups
que sobrevivem ao WP7 (não-bloqueantes): S7 enforcement R-A..R-D (`test_import_boundaries`); drain dos
`Action.label`/confirmation PT-BR → OmotenashiCopy (liga o scan PT-BR do R-B); blinding do payload do
endpoint Nuxt acoplado a matar o POS-HTMX legado (§5.1, cruza WP8 Arc D).
```bash
cd surfaces/pos-uithing-nuxt && export PATH="/opt/homebrew/bin:$PATH" && npx nuxi typecheck && npx vitest run
```
