# BACKSTAGE-EXCELLENCE-HARDENING-PLAN

> Excellence hardening das **quatro superfícies de operador** (`surfaces/pos-nuxt`,
> `orders-nuxt`, `kds-nuxt`, `production-nuxt`) + a nova central de operador
> **Central de Apps**. Segundo alvo da iniciativa "excellence hardening por app",
> herdando o harness provado no storefront (WP-S0..S6) e as duas lentes novas
> (consistência/pixel-perfect + omotenashi do operador).

**Status:** 🟢 EM ANDAMENTO — **as 5 superfícies adotaram o `OperatorRail`** (WP-B0.2);
**B-POS**, **WP-BH (Central)**, **B-ORD (Gestor)** e **B-PROD (Fournil)** com o hardening
COMPLETO (.0–.7). Falta o hardening por-WP do **KDS** (só recebeu o shell no WP-B0.2 —
tooling + cobertura .0–.6 pendentes).

### Registro de execução

- **WP-B0 · parcial ✅ (2026-07-04, commit da branch):** criado o Nuxt layer
  `surfaces/operator-kit/` e os **4 apps de operador passaram a `extends`** — build
  limpo nos 4 + suítes verdes (POS 68, KDS 21, Orders 66, Produção 27), auto-imports do
  layer verificados em cada `.nuxt`. Entregue no kit: resiliência (`httpError`/
  `isTransientError`, `retryWithBackoff` exp+jitter+teto), conectividade
  (`useConnectivity` + `OfflineBanner`), telemetria (`reportClientError` +
  `errorReporter.client`), **guardrail de paridade de tokens** (Lente 7 scaffold; 20
  testes do kit verdes). Django: `ClientErrorView` em `/api/v1/backstage/client-error/`
  (AllowAny, PII sanitizada, rate-limit; 8 testes verdes). **Additive-only** (nomes sem
  colisão) → zero regressão nos apps.
  - **Restante do B0 (follow-up, documentado no README do kit):** de-duplicação dos
    byte-idênticos `djangoProxy`/`tw-helper`/`translucent` (com ripple de imports/testes);
    consolidação da família **operator-lock** (diverge 2–3 variantes; POS tem tela
    própria) — é trabalho por-app; extração do bloco de **tokens do `tailwind.css`** pro
    kit (split do app-específico: print no POS, dark no KDS); **interceptor global de
    401/403**; instalação da **tooling parity** (ESLint/Prettier/vitest 2-projects/
    Playwright) por app — cada uma aterrissa no WP do respectivo app.
- **B-POS · ✅ / WP-BH (Central) · ✅ / B-ORD (Gestor) · ✅:** os três primeiros apps
  passaram pelos WPs `.1..7` (harness 2-project, cobertura test-first, e2e mock, lint 0,
  build, omotenashi). Harness provado com os workarounds do `@nuxt/test-utils` 4.0.3 (ver
  §4, correção). Central nova em `surfaces/hub-nuxt/` sobre o kit.
- **⚠️ Furo descoberto na demo (2026-07-06):** o WP-B0 entregou o kit **invisível**
  (resiliência, telemetria, guardrail de tokens, `OfflineBanner`), mas a **camada visível
  compartilhada que o §4 previa nunca foi construída** — `tailwind.css` ainda é copiado por
  app, primitivas `Ui/**` não extraídas, e **não existe shell/rail comum**. Resultado: os
  apps não "parecem" da mesma família. Correção = **WP-B0.2** (abaixo). Descartada a
  tentativa de top-bar `OperatorChrome` (unidade fraca demais); a assinatura passa a ser o
  **rail lateral neutro** (origem: `PosFunctionRail`), com **3 estados** que o operador
  escolhe (colapsado · compacto · estendido), persistidos por estação.

**Baseline de maturidade** (EXCELLENCE-AUDIT-2026-07): production 3.7 · kds 3.6 ·
pos 3.6 · orders 3.4 (storefront 4.4 é o exemplar de harness, **fora** da unificação
visual do operador).
**Branch:** `feat/backstage-excellence-hardening` (a branch do storefront é PR à parte).

---

## 1. O que a auditoria encontrou (2026-07-04, 4 agentes paralelos)

| | pos (PDV) | orders (Gestor) | kds | production (Fournil) |
|---|---|---|---|---|
| Nota (audit) | 3.6 | **3.4** | 3.6 | **3.7** |
| Componentes de domínio | 73 | 61 | 57 | 59 |
| Presentation (módulos) | **10** | 3 | 2 | 2 |
| — presentation testado? | ✅ | ❌ | ✅ | ✅ |
| Composables | 6 | 8 | 3 | **11** |
| — composables testados? | ❌ | ❌ | ❌ | ❌ |
| Força de assinatura | print/recibo, caixa, pagamento | drag-reorder, matriz de catálogo | SSE + beep, dark-first | `useAdaptivePoll` (visibility-aware) |
| Orientação | **desktop-first** | light | **dark-first** | light |

**Três fatos que governam todo o plano:**

1. **O design system já é canônico — por copy-paste.** Os quatro apps de operador
   embarcam um `tailwind.css` **token-idêntico** (mesmo `--radius: 0.5rem`,
   `--primary: oklch(0.27 0 0)` neutro, `--destructive` vermelho, a mesma escada
   tipográfica display→micro, a mesma escada de altura h-7/9/11/14, `rounded-md`
   default, tema zinc, Inter + Fira Code). Os quatro `server/utils/djangoProxy.ts`
   são **byte-idênticos (mesmo md5)**. **Não existe** pacote/layer/symlink/workspace
   compartilhado — é duplicação literal. A divergência é intencional e pequena: KDS é
   dark-first; o storefront é deliberadamente separado (branded: Instrument Sans +
   Fraunces, marrom quente, tokens semânticos extras) e **fica fora** da unificação.

2. **O gap de harness é uniforme.** Os apps de operador têm só `vitest` + `typescript`
   em dev. Nenhum tem ESLint/Prettier/Playwright/`@nuxt/test-utils`. Os testes cobrem
   **só presentation** (funções puras); o **código de risco é 100% não-testado** —
   todo composable de fetch/mutação/SSE/poll (`usePosSale` 1447 LOC, `useKdsBoard`,
   `useProductionBoard` + 10 irmãos, `useOrdersBoard`). Zero teste de componente, zero
   e2e, sem telemetria, sem lint.

3. **A auditoria transversal 2026-07 já fechou os bloqueadores de release**
   (re-gate de 401 nos boards, chip de autosave do POS, priming do beep do KDS,
   rollover de meia-noite da produção, deadline do gestor na projection, endpoint de
   PIX polling). Esta iniciativa é o **passo profundo por app POR CIMA** disso — as
   duas lentes novas + a paridade de harness + a cobertura que a varredura transversal
   não fez app a app.

**Exemplares (dois papéis distintos):**
- **Template de harness = `storefront-nuxt`** (o rig provado WP-S0..S6).
- **Exemplar canônico do operador = `pos-nuxt`** — o mais rico (73 comp / 10 módulos
  de presentation / print) e *desktop-first*, logo o âncora mais exigente do kit
  compartilhado e dos guardrails de DS. Provar o canon contra o POS de-risca os três
  mais leves.

---

## 2. As 8 lentes (6 originais + 2 novas)

As 6 lentes originais (herdadas de EXCELLENCE-AUDIT/STOREFRONT-HARDENING):
**Testabilidade · Resiliência · Fail-loud · Observabilidade · Elegância · Segurança.**

### Lente 7 (nova) — Consistência UI/UX + pixel-perfect entre os 4 apps

Critério de aceite: **familiaridade** entre PDV/KDS/Gestor/Fournil (o storefront fica
de fora). O design system canônico do backstage (ver §3 e
[`docs/engineering/backstage-design-system.md`](../engineering/backstage-design-system.md))
é a fonte única. Guardrails **como testes** (à la `surfaceGuardrails` do storefront):

- **Paridade de tokens** entre os 4 `tailwind.css` — falha no instante em que alguém
  edita um e não os outros (mata a divergência silenciosa que o copy-paste convida).
- **Escala respeitada** — sem raio arbitrário (`rounded-lg/xl` avulso), sem `ring` em
  seleção, só classes dos 6 papéis tipográficos, alvos de toque ≥ 44px.
- **Ícone forte por app** presente e correto (identidade/familiaridade).
- **A11y estrutural** — corrige o `aria-hidden` porém focável do input de crachá
  (WCAG 4.1.2) nos 4 apps; ordem de foco; rótulos.
- **Shell compartilhado (`OperatorRail`) adotado, não copiado** — a unidade forte vem de
  um **componente do kit**, não de pixel replicado: a mesma espinha lateral neutra
  (`bg-primary`) em todos, com o ícone forte do app no topo, as **funções comuns** na base
  (voltar à Central, operador/travar, tema, atualizar/conexão) e **3 estados** (colapsado ·
  compacto · estendido) que o operador cicla e ficam persistidos por dispositivo. Nav
  específica de cada app (abas do Gestor, visões do Fournil) fica no conteúdo — o rail
  economiza a horizontal e concentra só o comum. "Nivelar à canon" = **adotar o shell +
  apagar a cópia divergente**.

### Lente 8 (nova) — Omotenashi do operador

Critério de aceite: **nada quadrado, nada prolixo, nada no vácuo** — poder de síntese
sem perder a essência. Detalhes de confiança no trabalho:

- Estados de **erro/vazio/loading acolhedores** (não "tela branca", não empty-state
  mentiroso quando é erro de API); dado velho visível > quadro vazio.
- **Feedback nunca no vácuo** ([[feedback_validate_early_inline]],
  [[feedback_transparent_timeouts]]): toda ação e todo TTL do operador têm retorno.
- **Foco/teclado** first-class; **toque grande** no PDV; **leitura à distância** no
  KDS/produção (tipografia mono tabular, contraste, tamanho a ~2m).
- Acessibilidade + omotenashi first-class ([[feedback_accessibility_omotenashi_first_class]]).

---

## 3. Design system canônico do backstage

Documentado em [`docs/engineering/backstage-design-system.md`](../engineering/backstage-design-system.md).
Resumo do que vira contrato (os tokens já existem idênticos; o passo é **promovê-los a
documentado + guardrailado**):

- **Cor:** OKLch neutro (`--primary 0.27`, cor só com significado — vermelho=destrutivo,
  âmbar=aviso, verde=dinheiro/sucesso). Sem matiz de marca no operador (disciplina
  Odoo/ERP). O storefront mantém o sistema branded próprio.
- **Escada tipográfica** (6 papéis): `display` → `figure` → `title` → `body` (workhorse)
  → `label` → `micro`.
- **Escada de altura de controle:** h-7 / h-9 / **h-11 (44px, toque-seguro default)** /
  h-14 (CTA/numpad/tile).
- **Espaçamento:** gap 1.5/2/3/4/6; `rounded-md` default, `rounded-full` só pílula.
- **Ícone forte por app** (Lucide): PDV `banknote`, KDS `chef-hat`, Gestor
  `clipboard-list`, Fournil `croissant`, Loja `store`, Central `layout-grid`.
- **Rail de operador (`OperatorRail`, primitiva do kit):** espinha vertical **neutra**
  (`bg-primary` ≈ preto — sem matiz de marca, coerente com a cor já neutra do operador),
  ícone forte do app no topo + controle de estado, funções comuns na base. **3 estados**
  persistidos: `colapsado` (puxador fino) · `compacto` (só ícone, ~w-14, o de hoje no POS) ·
  `estendido` (ícone + rótulo). É o portador nº 1 da familiaridade — mesma peça em todos.
- **Intenção por superfície (canônica, não drift):** KDS dark-first + timers mono à
  distância; produção light-first + board Solari; POS densidade desktop; gestor board.

**Scaffold dos guardrails** = suíte vitest compartilhada no `operator-kit` (ver §4),
consumida pelos 4 apps.

---

## 4. Receita do harness — `operator-kit` (Nuxt layer)

**Decisão (aprovada):** como o código compartilhado é *literalmente duplicado hoje*,
copiar o harness do storefront em cada app multiplicaria a dívida por quatro. Em vez
disso, extraímos o invariante UMA vez para um **Nuxt layer** `surfaces/operator-kit/`
que os 4 apps (+ Central de Apps) fazem `extends`. Mata o copy-paste, testa
BFF/resiliência **uma vez**, e cada app segue deployando independente.

**O que vive no `operator-kit`:**
- `server/utils/djangoProxy.ts` (hoje byte-idêntico nos 4) + testes de BFF.
- Resiliência: `retryWithBackoff`/`httpError`/`isTransientError`, `useConnectivity` +
  `OfflineBanner`, **interceptor global de 401/403** (reabre o gate de operador),
  timestamp de último sucesso → banner por idade do dado.
- `useOperatorLock` + `presentation/operatorLock.ts` (hoje replicados nos 4).
- Telemetria: `clientErrorReport` util + plugin `errorReporter.client` (inerte em dev,
  dedupe+cap, PII sanitizada) → novo endpoint Django `backstage/client-error/`.
- Design system: `assets/css/tailwind.css` (tokens canônicos) + primitivas `Ui/**` +
  **shell**: `OperatorRail` (3-estados neutro) + `RailItem` + `useRailState` (persistência) +
  estados vazio/erro/loading acolhedores compartilhados.
- Guardrails: suíte vitest de consistência (paridade de token, escala, a11y).
- Tooling: config base de ESLint flat (`@nuxt/eslint`) + Prettier + vitest 2-projects
  + Playwright + `mockBackend.mjs`.

> **Correção da receita (provada em B-POS/B-ORD):** o `@nuxt/test-utils` 4.0.3 **quebra o
> env `nuxt`** no setup de apps com router (`nuxtApp._route` undefined). Os 2 projects NÃO
> usam env nuxt: **`unit`** roda composables em **env node** com `vi.stubGlobal` para os
> auto-imports do Nuxt (reatividade Vue real, fronteira de dados mockada — ver
> `tests/support/composableEnv.ts`); **`component`** roda em **happy-dom + `@vitejs/plugin-vue`**
> com `@vue/test-utils` `mount()`; **e2e** Playwright contra `mockBackend` + build de produção.

**O que fica em cada app:** pages, componentes de domínio, composables de domínio,
`presentation/` específico, `nuxt.config.ts` (com `extends: ['../operator-kit']` +
override de color-mode: KDS `dark`, demais `light`).

**Storefront:** permanece independente (harness branded próprio, já entregue). Não
consome o `operator-kit`.

---

## 5. Central de Apps — a central do operador (design; build é sessão dedicada)

**Decisão (aprovada):** app Nuxt dedicado **"Central de Apps"** em
`central.boulangerie.com.br`. Estilo home do Odoo: pós-login o operador cai numa
central que dá acesso aos apps **registrados** (PDV · Produção · KDS · Gestor · Loja),
cada um com **ícone forte**, **permission-aware** (app sem permissão nem aparece).

### Resolução da tensão com o Unfold Canonical Gate

A Central é um app Nuxt novo — precisa se acertar com o Gate. O próprio Gate tem a
saída explícita ([`unfold_canonical_policy.md`](../engineering/unfold_canonical_policy.md)
linha 36 e 119): *"New backstage templates must land in a canonical Admin/Unfold
surface **or an explicit registered runtime surface with a product reason**"* +
*"registered backstage runtime templates that are allowed to exist only as explicit
operator experiences"*. Resolução:

- A Central entra como **superfície runtime registrada** (mesma categoria de
  `pos-nuxt`/`kds-nuxt`), com **product reason** explícito: é o **entry-point/launcher**
  do operador que unifica as superfícies dedicadas real-time via o MESMO contrato
  projection+Action. **Não** hospeda CRUD de Admin.
- O tile **Loja → configurações da loja online** **deep-linka para o Unfold canônico**
  (a config real de loja continua no Admin/Unfold; a Central só a lança + oferece
  "Abrir o site"). Assim mantém-se coerente o princípio "Unfold para gestão/config,
  dedicado para operar/lançar" ([[feedback_no_standalone_admin]],
  [[project_excellence_refactor_initiative]]).
- Não adiciona template de Admin → não amplia a superfície escaneada pelo gate; entra
  no `unfold_canonical_inventory.md` como runtime surface autorizada.

### Contrato & auth (nada de infra nova de sessão)

- **Projection** `shopman/backstage/projections/hub.py` → `build_operator_hub(user)`
  sobre um **registro declarativo** de apps (começa como registry tipado em
  `backstage/`, com caminho claro para configurável no Admin depois —
  [[feedback_dataclass_driven_admin]]). Cada tile tem `can_access` = predicado de
  permissão (`can_operate_pos/kds`, `can_manage_orders`, `can_access_production`).
- **API** `GET /api/v1/backstage/hub/` (segue a forma dos outros builders).
- **Auth:** reusa o cookie cross-subdomínio `.boulangerie` + `OperatorSessionDomainMiddleware`
  ([[project_operator_apps_crosssubdomain_auth_gap]]) — **zero trabalho novo**.
- **Entry-point:** landing do operador / `LOGIN_REDIRECT_URL` → Central; host novo
  `central.boulangerie.com.br` (add em `.do/app.subdomains.yaml` + ingress +
  ALLOWED_HOSTS/CSRF). Consome o `operator-kit` como 5º cliente.

---

## 6. Work Packages

### WP-B0 · Fundação (o kit compartilhado) — PRÉ-REQUISITO de tudo

- Cria `surfaces/operator-kit/` (Nuxt layer) com todo o conteúdo do §4; os 4 apps
  passam a `extends`.
- Extrai `djangoProxy.ts` (4 cópias → 1 no kit) + testes de BFF.
- Instala paridade de tooling (ESLint flat + Prettier + vitest 2-projects + Playwright
  + `mockBackend.mjs`) via kit.
- Escreve `backstage-design-system.md` + a **suíte de guardrails** (scaffold).
- Novo endpoint Django `backstage/client-error/` (espelha `storefront/client-error/`,
  PII sanitizada, rate-limit) — muda só em `shopman/backstage/`.
- **Aceite:** cada app builda com o layer; baseline de testes verde por app; lint 0 no
  kit; guardrails rodando (mesmo que com allowlist inicial de dívidas conhecidas).

### WP-B0.2 · A camada VISÍVEL compartilhada (o shell) — fecha o furo do B0

O que o B0 deixou de fora, agora explícito. Origem do rail = o `PosFunctionRail` do POS,
generalizado.

- **`OperatorRail.vue`** (kit): rail vertical neutro (`bg-primary`), **3 estados**
  (colapsado · compacto · estendido) via **`useRailState`** (persistência por dispositivo,
  cookie/localStorage; SSR-safe). Topo: controle de estado + ícone forte do app (+ rótulo
  no estendido). Base (comum): voltar à Central, operador/travar (`@lock`), tema,
  atualizar/conexão. Slots `#nav` (funções específicas do app) e `#status`.
- **`RailItem.vue`** (kit): primitiva de item do rail — ícone + rótulo (no estendido) +
  tooltip (no compacto/colapsado) + `aria-label`/`aria-current`; consistente nos 3 estados.
- **Estados vazio/erro/loading** compartilhados (Lente 8) promovidos ao kit.
- **Adoção-prova no POS:** `PosFunctionRail` → consome `OperatorRail` (board/caixa/health
  nos slots), **apagando a divergência**. Regressão-zero: suíte POS verde + build.
- **Aceite:** rail nos 3 estados no POS (visual aprovado); `useRailState` testado
  (ciclo + persistência, test-first, env node); lint 0 + build; guardrails verdes.

### Passo de revisão · POS · Gestor · Central (antes de KDS/PROD)

Os três já hardenados adotam o shell e recebem o polimento final de Lentes 7+8:
- **POS** — origem do rail (adoção acima); confere densidade desktop + os 3 estados.
- **Gestor** — troca o `GestorTopBar`/`OperatorChrome` pelo `OperatorRail`; a nav de seção
  (Pedidos/Catálogo/Expositores) fica no topo do **conteúdo**, não no rail.
- **Central** — reverte o `OperatorChrome` (saudação desmontada); adota o rail sem botão
  "Central" (é a casa) e sem travar; a grade de apps é o conteúdo.
- Descartar `OperatorChrome.vue` (beco sem saída).

### Por app (cada um = uma sessão), na forma S1–S6 do storefront + Lentes 7 e 8

Padrão de WP por app `<APP>` ∈ {POS, ORD, KDS, PROD}:

- **B-`<APP>`.1 · Testes de composables/estado** (o gap grande): fila otimista+rollback,
  ramos de erro (401/409/429/rede), SSE/poll, auth. Ex.: `usePosSale` (1447 LOC),
  `useKdsBoard`, os 11 da produção, `useOrdersBoard`, e o `presentation/` não-testado
  do gestor.
- **B-`<APP>`.2 · BFF** — coberto uma vez no kit; o app só valida o wiring.
- **B-`<APP>`.3 · Resiliência/observabilidade** — herda do kit (backoff, offline,
  401-interceptor, telemetria) + específicos: **POS** finalizar UI do PIX polling;
  **Gestor** indicador de degradação de SSE + countdown do deadline no card; **Produção**
  staleness/adaptive-poll; **KDS** honestidade do `retirada` (bolinha "ao vivo" só se
  vivo) + beep.
- **B-`<APP>`.4 · Type-safety + dead code + lint 0** — `any`→`unknown`+guards; poda dos
  ~40 componentes `Ui/**` mortos por app (com justificativa de retenção onde for
  família vendada); `catch` tipado.
- **B-`<APP>`.5 · E2E Playwright** (backend-independente, à la storefront): gate de
  operator-lock, offline, re-gate de 401, boards vazio/erro, 404. Fluxo com dados =
  spec `skip` documentado p/ reviewer local.
- **B-`<APP>`.6 · Component tests** dos componentes de risco: **POS**
  `PosPaymentWorkspace`/`PosCartPanel`; **Gestor** `OrderCard` (countdown);
  **KDS** `KdsTicketCard`; **Produção** `ProductionStageGrid` (multi-lote).
- **B-`<APP>`.7 · (Lentes 7+8) Omotenashi + pixel-perfect** — erro/vazio/loading
  acolhedores; foco/teclado; toque ≥44px; leitura à distância (KDS/produção);
  conformidade aos guardrails de DS; correções WCAG.

### WP-BH · Central de Apps — sessão dedicada

Constrói o §5: projection `build_operator_hub` + `/api/v1/backstage/hub/` + app
`surfaces/hub-nuxt/` (Central de Apps) sobre o `operator-kit`; registro de superfície
runtime no inventário Unfold; host `central.` + ingress; entry-point pós-login.

---

## 7. Sequência

```
WP-B0   ✅ (kit invisível: resiliência + telemetria + guardrails de token)
  → B-POS   ✅ (âncora desktop-first)
  → WP-BH   ✅ (Central de Apps)
  → B-ORD   ✅ (Gestor)
  → WP-B0.2  ✅ a camada VISÍVEL (OperatorRail 3-estados) — POS·Gestor·Central·KDS adotaram
  → B-PROD   ✅ (Fournil; hardening full .0–.7 + rail; 91 unit/comp + 5 e2e) 2026-07-06
  → B-KDS    ⏳ FALTA (dark-first, SSE) — KDS só recebeu o SHELL no WP-B0.2; tooling+cobertura
             (.0–.6) ainda pendentes: composable-tests, resiliência (honestidade do `retirada`
             + beep), type-safety, e2e, component-tests.
```

> O furo da demo (2026-07-06) reordenou o fim: primeiro se construiu o shell VISÍVEL
> (WP-B0.2) e se adotou em POS/Gestor/Central/KDS/Fournil; o Fournil recebeu o hardening
> COMPLETO. Resta o hardening por-WP do KDS (só o shell foi feito).

## 8. Gate de cada WP (não-negociável)

1. Baseline verde antes de começar.
2. Todo gap/bug vira teste que falha → fix → suíte verde.
3. `npm run test` (unit+component) verde + `npm run lint` 0 + `npm run build` sem erro.
4. Guardrails de DS verdes (sem nova violação; dívida conhecida sai da allowlist ao
   ser resolvida, nunca cresce).
5. Commit atômico por WP; zero resíduo ([[feedback_zero_residuals]]).
6. Core sagrado — `packages/` intocado; Django só em `shopman/backstage/`.

## 9. Fora de escopo (registrar, não fazer)

- App de **B.I. (Business Intelligence)** — frente futura separada.
- Multi-tenant / registro de apps configurável no Admin — a Central nasce com registry
  server-side; a configurabilidade via Admin é evolução declarada, não deste ciclo.
- PWA/service-worker offline real nos operadores (só sinal de conexão nesta onda).
- Storefront — tem harness e padrão próprios; não entra na unificação visual.
