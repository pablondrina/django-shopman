# WP7 — PDV limpo (Ponto de Venda) · kickoff autossuficiente

> Prompt de abertura para uma sessão limpa. Branch `redesign/surface-excellence`.
> Pilar **Ponto de Venda** da Iniciativa de Excelência. Fase 3 do redesign.
> WP1 (arquitetura) + WP2 (spec PDV) + WP4 (read-side storefront) + WP5 (instância) + WP8 (backoffice)
> já FEITOS. Agora é a vez do PDV.

## Autonomia & postura

**AUTONOMIA TOTAL** (Pablo concedeu, 2026-06-06): decidir por mérito e prosseguir sem perguntar.
NUNCA otimizar por menor-diff/menor-esforço — só a solução mais correta/robusta/elegante pelo mérito
(`feedback_never_recommend_smallest_diff` — Pablo já corrigiu isso no D2 do WP6). Zero gambiarra, zero
residual em renames/deleções, **não inventar features**. Verde a cada passo; commits coerentes por arco.

**Core SAGRADO.** `packages/` (9 apps) intocável sem autorização EXPLÍCITA do Pablo. `shop/` é
orquestrador (editável) mas **cada mudança SINALIZADA**. Antes de "o Core não cobre", assumir que
cobre e procurar onde (`feedback_respect_core_no_reinvent`).

## LER PRIMEIRO (obrigatório, antes de mexer)

**Spec & arquitetura (fonte da verdade):**
- `docs/redesign/05-spec-pos.md` — **a spec do PDV**. Tenets, telas, contrato. Define *o quê*; layout
  (D2) e impressão (D3) são "fase de shell", não bloqueiam o contrato.
- `docs/redesign/04-architecture.md` + `docs/decisions/adr-014-surface-data-presentation-cut.md` —
  contrato **`Projection`(dado) / `Action` / `Presentation`(aparência)**. As 3 camadas. A regra de ouro.
- `docs/redesign/02-confronto.md` — decisões D1–D7 (D1 manager-approval por-permissão; D2 layout
  cart-dir×ticket-esq = adiado p/ shell; D3 PDV web/Nuxt mantido).
- `docs/redesign/PLAN.md` seção **WP7** (inclui a pendência herdada **E3/E4** — ver abaixo).

**Memórias:**
- `project_excellence_refactor_initiative` — ⭐ objetivo-mãe, processo, corte dado/apresentação,
  "superfície = apresentação pura, NÃO contaminar com a arquitetura frankenstein".
- `project_pos_uithing_redesign_goal` — POS→UI Thing, benchmarks (Shopify/STORES/Take.app/Odoo),
  modelagem de comanda/move_lines/fire-kitchen/PIN, **contrato cliente já consolidado** (reusar).
- `project_pos_visual_fidelity_deep_dive` — feedback duro do Pablo sobre aparência/fluidez (payment
  screen estilo Odoo, alturas fixas, Hyper Focus, não-formulário). Vale na fase de shell visual.
- `project_pos_staging_deploy` — deploy staging DO, gotchas. `project_backstage_pos_test_pollution`
  — **NÃO usar `make test-framework`** (RED pré-existente não-determinístico POS/KDS).

**Benchmarks:** `docs/research/pos-benchmarks/` (README + synthesis + shopify/stores/take-app).

## Estado atual (auditado 2026-06-06 — ser honesto, não re-descobrir)

- **Nuxt `surfaces/pos-uithing-nuxt/` EXISTE com muito trabalho prévio** (Fases 1–5 do plano antigo
  `POS-UITHING-REDESIGN-PLAN.md`: PIN/lock, comanda, checkout 3-zonas, caixa, fire-kitchen, anti-fraude).
  **MAS o `app.vue` é o "frankenstein" que o Pablo rejeitou.** Postura: **reconstruir a camada de UI
  limpa per `05-spec`, pescando bons padrões — NÃO copiar o app.vue.**
- **REUSAR (é ouro, a spec manda preservar):** o **proxy Nuxt** (`server/utils/djangoProxy.ts`, CSRF
  handshake) e o **contrato cliente consolidado** (`app/utils/posIntent.ts`, `app/types/pos.ts`,
  `operatorAccess.ts`). O redesign reescreve a UI, **não** o transporte/contrato.
- **Backend read-side NÃO drenado (S4 pendente):** `shop/services/pos.py` ainda tem **2179 linhas**
  misturando orquestração (FICA) + payload-de-UI (DRENA p/ `backstage/projections/pos.py`). Já existe
  `backstage/projections/pos.py` (1421ln) e `backstage/presentation/pos.py` (252ln, nasceu no WP8 Arc D).
- **Contrato POS duplicado client↔server:** `posIntent.ts` (139ln) ↔ `build_session_ops` (pos.py:955)
  sincronizados **à mão**. A spec pede **schema POS compartilhado gerado** p/ matar a dupla manutenção.
  **Não há gerador hoje** — desenhar (decisão de ferramenta abaixo).
- **POS-HTMX (Django) já virou transporte puro** no WP8 Arc D (presentation/pos.py). O PDV-Nuxt é a
  superfície canônica; a do Django (`backstage/views/pos.py` + templates HTMX) é a alternativa servida.
- **Pendência herdada E3/E4** (decisão Pablo 2026-06-06): labels PT→`OmotenashiCopy` (E3) + cores→enum
  `tone` (E4), hoje `CharField` serializados no REST p/ o Nuxt. Fazer **aqui**, no passe do contrato
  REST/schema (ancorado em `PLAN.md` §WP7). ~15 sites storefront+backstage.

## Princípio central do WP7

O PDV é **apresentação pura, headless/Nuxt** (UI Thing), consumindo `Projection`(dado) + `Action[]`
do orquestrador via **REST + proxy**. **Zero política, zero Core, zero HTML-em-view, zero aritmética
de preço/disponibilidade no cliente.** A `Presentation` do PDV é **TypeScript no Nuxt**
(`surfaces/pos-uithing-nuxt/.../presentation/` — pasta a nascer) que dá shape de tela à `Projection`
serializada. A **mesma** `Projection` que storefront/admin/agentic consomem.

## Plano de arcos proposto (cada um verde; commit coerente por arco)

> WP7 é uma empreitada grande (como WP6 teve arcos A→D e WP8 A→F). Decidir/ajustar a granularidade
> por mérito, mas a **ordem dado→contrato→apresentação→shell** é inegociável (arquitetura).

- **Arc 1 — Seam de dado & contrato (S4 + schema compartilhado).** Drenar o payload-de-UI de
  `shop/services/pos.py` (2179ln) → `backstage/projections/pos.py` (DADO frozen, política fica no
  write-side de services); **commit/saga/`build_session_ops` FICAM em services** (espinha sagrada).
  Desenhar o **schema POS compartilhado** que mata a dupla manutenção `posIntent.ts`↔`build_session_ops`
  (gerar tipos TS a partir de uma fonte única). **E3/E4 entram aqui** (labels→OmotenashiCopy, cores→tone
  no serializer, contrato Nuxt byte-compatível). **Este é o começo inequívoco — ver "Começar por".**
- **Arc 2 — Presentation TS + telas núcleo.** Nasce `surfaces/pos-uithing-nuxt/.../presentation/`;
  reconstruir Operator Lock (§2.1) / Sale Workspace (§2.2) / Tab Board (§2.3) consumindo a
  `Projection`+`Action` serializadas (sem reimplementar política no cliente). Reusar proxy + contrato.
  > Nomenclatura: **Tab = comanda** (pt-br). O termo canônico no código é `POSTab`/`pos_tab` (Python +
  > Nuxt). NÃO usar "Command/Command Board" — é tradução errada de "comanda". A tela do mapa de comandas
  > abertas é o **Tab Board** (spec §2.3 "Comanda / mesas").
- **Arc 3 — Checkout/pagamento + manager-PIN por-permissão + caixa cego.** Tela de pagamento dedicada
  estilo Odoo (não-formulário, ver `project_pos_visual_fidelity_deep_dive`); `requires_manager_approval`
  por flag (D1); caixa cego.
- **Arc 4 — move_lines / fire-to-kitchen progressivo.** Split/transfer/merge com **preço congelado**;
  `fired_lines`. (move_lines = op de kernel **pré-autorizada** no plano, MAS surfacear o diff
  explicitamente antes de aplicar.)
- **Arc 5 (shell visual) — D2 layout + D3 impressão + fidelidade de benchmark.** Linguagem de layout
  única, alturas fixas, Hyper Focus, fluidez Shopify. Decisões D2/D3 aterrissam aqui.

## Decisões abertas (decidir por mérito / confirmar com Pablo quando tocar)

- **D2 — layout cart-direita (Shopify) × ticket-esquerda (Odoo/atual):** adiado p/ shell (Arc 5). É
  apresentação, trocável. Sem dados de A/B; é convenção/ergonomia.
- **D3 — impressão sem fricção (Ubuntu):** kiosk-printing OU ePOS de rede — prototipar no Arc 5.
- **Ferramenta de schema compartilhado (Arc 1):** escolher por mérito (ex.: dataclass→JSON Schema→
  tipos TS, ou pydantic/openapi). Fonte única no orquestrador; TS gerado, não escrito à mão.

## NÃO FAZER

- **Não tocar o Core** (`packages/`) sem autorização explícita — exceto `move_lines` (Arc 4,
  pré-autorizado) e ainda assim **surfacear o diff antes**.
- **Não copiar o `app.vue` frankenstein.** Reconstruir limpo per spec.
- **Não inventar features** (notify-me, ACP, WhatsApp-in-chat in-scope do WP9 — não pré-emptar).
- **Não reimplementar política no cliente** (preço/disponibilidade/gates vêm do orquestrador).

## Gates (verde ao fim de cada arco)

- `pytest shopman/shop/tests shopman/backstage/tests -q` — **NÃO** `make test-framework`
  (`project_backstage_pos_test_pollution`). Para o drain do read-side, validar também
  `pytest shopman/shop/tests storefront/tests` se tocar fronteira storefront.
- `cd surfaces/pos-uithing-nuxt && npx nuxi typecheck` (ignorar erros pré-existentes conhecidos em
  `djangoProxy.ts`/`nuxt.config.ts`) + `vitest`.
- `make admin` se tocar qualquer superfície Admin/Unfold (improvável no PDV, mas o serializer E3/E4
  pode cruzar).
- Preview ao vivo (`preview_*`): Django :8000 (admin/admin), Nuxt :3002 via **127.0.0.1** (gotcha IPv6
  426), PIN operador **1234**. Screenshot de prova das telas tocadas.

## Começar por

1. Ler a spec `05-spec-pos.md` + `04-architecture.md` + adr-014 + as memórias. Montar o mapa mental do
   contrato Projection/Action/Presentation **antes** de editar.
2. **Arc 1, passo 1 — auditar `shop/services/pos.py` (2179ln):** separar, linha a linha de
   responsabilidade, o que é **orquestração/saga/política/`build_session_ops`** (FICA em services) do
   que é **payload-de-UI** (DRENA p/ `backstage/projections/pos.py`). Surfacear o mapa antes de cortar.
3. **Arc 1, passo 2 — desenhar o schema POS compartilhado** (fonte única → tipos TS gerados), matando
   a sync manual `posIntent.ts`↔`build_session_ops`. Escolher a ferramenta por mérito.
4. **Arc 1, passo 3 — E3/E4** no serializer (labels→OmotenashiCopy, cores→tone→classe), contrato Nuxt
   preservado byte-a-byte.
5. Verde + commit coerente. Seguir p/ Arc 2. Atualizar a memória ao fim de cada arco.
