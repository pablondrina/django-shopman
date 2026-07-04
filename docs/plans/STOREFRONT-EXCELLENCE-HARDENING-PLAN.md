# STOREFRONT-EXCELLENCE-HARDENING-PLAN

> Excellence hardening da superfície **storefront-nuxt** (Nuxt 4 SSR, loja do
> cliente). Primeiro alvo da iniciativa "excellence hardening por app".
> Metodologia herdada de HARDENING-PLAN(1/2/3), SPLIT-HARDENING-PLAN e
> EXCELLENCE-AUDIT-2026-07 (6 lentes + 4 ondas, test-first, regressão-zero).

**Status:** 🟢 em execução — WP-S0 ✅ · WP-S1 ✅ · WP-S2 ✅ · WP-S3 ✅ · WP-S4 ✅
**Data:** 2026-07-04
**Baseline:** storefront-nuxt = 4.4⭐ na EXCELLENCE-AUDIT (a superfície mais madura).
Isto é **reforço de excelência**, não conserto de podridão.

### Registro de execução

- **WP-S0 ✅ (2026-07-04):** baseline de testes travado em **verde** (corrigidas 2
  dívidas de guardrail em `entrar.vue`: `text-2xl`→`text-3xl`, `text-[0.65rem]`→
  `text-xs`, `gap-1.5`→`gap-2`). Tooling: vitest com 2 projects (`unit` env node +
  `component` env nuxt/happy-dom via `@nuxt/test-utils`), smoke de componente verde
  (229 testes). ESLint (`@nuxt/eslint` flat) + Prettier: `vue/require-default-prop`
  desligada (ruído de UI lib); **baseline de lint = 106 problemas significativos**
  (92 `no-explicit-any`, 7 `no-dynamic-delete`, 2 `no-v-html`, 4 misc) → alvo do
  WP-S4. Security sweep OK (sem segredo em env; robots bloqueia rotas privadas).
  Build de produção verde. Scripts: `test:unit`, `test:component`, `test:e2e`,
  `lint`, `lint:fix`, `format`.
- **WP-S1 ✅ (2026-07-04):** cobertura test-first dos composables de estado (env
  nuxt, `$fetch` stubado como global). **+23 testes** (252 no total): `useCartState`
  (9 — optimistic+drain, fila serial em ordem, 409 substitutos, 429 retry-after,
  erro genérico, retry/acceptAvailableQty/addSubstitute, preservação de cartIssue),
  `useShopSession` (6), `useFavoritesState` (4 — optimistic+revert+anon no-op),
  `useReorder` (4 — sucesso+navega, 409 conflito, performAction). `no-explicit-any`
  desligado só em `tests/**` (test doubles). Conversão `catch(any)→unknown`
  consolidada no WP-S4.
- **WP-S2 ✅ (2026-07-04):** BFF `proxyDjangoPath` testado ponta a ponta com H3Event
  real (mock `http.IncomingMessage/ServerResponse`) + `$fetch.raw` stubado. **+5
  testes** (257 no total): reescrita de origin/referer p/ o Django + injeção de
  x-csrftoken em método unsafe; GET safe não força CSRF nem body e preserva query;
  status upstream 409 preservado com corpo cru (sem envelope); set-cookie
  split-aware nas duas direções; handshake de CSRF quando falta token. (Passthrough
  de corpo fica p/ o e2e — limitação do mock de stream sob vitest.)
- **WP-S3 ✅ (2026-07-04):** resiliência de rede + observabilidade.
  - **S3a** `retryWithBackoff` (exponencial+jitter+teto+cap, injetável) +
    `httpError/isTransientError`; fila de mutação do carrinho retenta soluço
    transiente (rede/502/503/504) sem martelar, `catch(any)→unknown`. +8 testes.
  - **S3b** `useConnectivity` (VueUse) + `OfflineBanner`: reconexão/retorno de foco
    reconcilia o carrinho; banner calmo global. +3 testes.
  - **S3c** `trackingFreshness` "Atualizado há X" no tracking, vira aviso ao perder
    poll; guardrail atualizado. +5 testes.
  - **S3d** telemetria espelhando o Sentry opt-in do Django: endpoint
    `storefront/client-error/` (sem CSRF, rate-limit 30/m, loga→Sentry) + plugin
    Nuxt `errorReporter.client` (inerte em dev, dedupe+cap). PII sanitizada nos dois
    lados. +8 Django, +7 Nuxt. Storefront Django 627✅, Nuxt 280✅, build✅.
- **WP-S4 ✅ (2026-07-04):** type-safety + dead code + **lint a ZERO** (de 106
  problemas significativos → 0). `no-explicit-any` eliminado no NOSSO código (~57):
  catch `any`→`unknown`+`httpError`/`errorDetail` (util novo), parsing defensivo do
  carrinho `any`→`unknown`+`asRecord`, **Google Maps tipado de verdade**
  (`@types/google.maps` em AddressPicker+useGoogleMaps, zero `any`). `no-dynamic-
  delete` (7)→`omitKey` (util novo, destructuring). `no-v-html` (2): Ui/Card
  vendado desligado na override; ShopHeader com disable inline justificado (SVG
  curado no Admin). Dead code removido (clickHeroTab no smoke). Override eslint p/
  primitivas vendadas `Ui/**` (idioma ui-thing). 280✅, build✅.
  - ⚠️ **Follow-up (fora do escopo do S4):** ~12 erros de `nuxi typecheck`
    PRÉ-EXISTENTES (o gate nunca teve typecheck) — spawn task criado. Nenhum nos
    arquivos tocados aqui; a tipagem nova compila limpa.

---

## Princípios (não-negociáveis)

1. **Test-first, regressão-zero.** Capturar baseline `npm run test` (verde) antes do
   1º WP. Todo bug/gap vira teste que falha → fix → suíte inteira verde. Qualquer
   regressão = revert.
2. **Core é sagrado.** Nada aqui toca `packages/`. Mudanças no Django limitam-se a
   `shopman/storefront/` (ex.: rota de ingestão de erro) e só quando indispensável.
3. **Sem inventar feature.** Sinais de offline/staleness usam dado que a API já
   expõe; não criamos capacidades que o backend não cumpre
   ([[feedback_no_overpromise_tracking]]).
4. **Zero gambiarra.** Solução correta e elegante, nunca menor-diff
   ([[feedback_never_recommend_smallest_diff]], [[feedback_zero_gambiarras]]).
5. **Espelhar padrões existentes.** Telemetria segue o modelo opt-in/à-prova-de-
   ausência do Sentry já presente em `config/settings.py`.

## Lentes × gaps reais (mapeados no código, 2026-07-04)

| Lente | Gap concreto | Onda |
|---|---|---|
| Testabilidade | composables (`useCartState`, `useShopSession`, `useFavoritesState`, `useReorder`) e BFF (`djangoProxy`, exceto CSRF) **sem teste**; zero teste de componente/página/e2e | S1, S2, S5 |
| Resiliência | fila de mutação **sem backoff/jitter/cap** (`useCartState.ts:159/267`); 429 sem countdown de auto-retry | S3 |
| Fail-loud | `catch (error: any)` engole tipo; fetch de página pode falhar em silêncio | S1, S4 |
| Observabilidade | sem telemetria client/BFF (Django já tem Sentry opt-in); sem sinal offline/staleness | S3 |
| Elegância | 238 componentes sem auditoria de uso; **sem ESLint/Prettier**; `any` defensivo | S4 |
| Segurança | perímetro público OK (BFF normaliza origin/referer + semeia CSRF); só varredura de confirmação | S0 |

---

## Ondas & Work Packages

### Onda 0 — Perímetro (confirmação, P0)

**WP-S0 · Foundation & security sweep**
- Baseline: rodar e registrar `npm run test` (contagem verde) + `npm run build`.
- Tooling (habilita todas as ondas seguintes):
  - Split do vitest em dois projetos: `unit` (env `node`, presentation+composables+BFF)
    e `component` (env `jsdom` + `@vue/test-utils` + `happy-dom`/`jsdom`).
  - Playwright para e2e (config isolado, roda contra `nuxt preview` + Django de teste;
    marcado `@e2e`, fora do `npm run test` default para não pesar CI unit).
  - ESLint (flat config, `@nuxt/eslint`) + Prettier alinhados às convenções do repo
    (HTMX/Alpine não se aplicam aqui; regras Vue/TS + import order). `npm run lint`.
- Security sweep (checklist, sem código salvo achado):
  - `.env.example` sem segredo real; `NUXT_DJANGO_BASE_URL` é o único runtime secret-ish.
  - Headers repassados pelo BFF conferidos (nenhum header sensível vaza p/ cliente).
  - `robots.txt`/`sitemap.xml` não expõem rotas de conta.
- **Aceite:** `npm run test` (unit) verde; `npm run lint` limpo; Playwright roda 1 smoke;
  baseline documentado no topo deste plano.

### Onda 1 — Fail-loud + cobertura de estado (P1)

**WP-S1 · Testes de composables de estado (test-first)**
- `useCartState`: fila serial (`enqueueMutation`), optimistic + rollback no drain,
  ramos 409 (SubstituteSheet) e 429 (retryAfter), `retryLastMutation`, preservação de
  `cartIssue` em refresh passivo. Mockar `$fetch`.
- `useShopSession`: hidratação SSR, estado de auth, transições.
- `useFavoritesState`, `useReorder`: toggle/fetch e caminhos de erro.
- **Aceite:** cada composable com fetch/estado tem teste cobrindo sucesso + ≥1 erro;
  ramos 409/429/network do carrinho cobertos explicitamente.

**WP-S2 · Testes do BFF (djangoProxy) além do CSRF**
- Repasse de cookies bidirecional, `set-cookie` split-aware, preservação de status em
  4xx/5xx (`ignoreResponseError`), normalização origin/referer em métodos unsafe,
  seed de CSRF quando ausente.
- **Aceite:** matriz de status (200/302/403/409/429/500) e cabeçalhos verificada.

**WP-S4-a · Fail-loud tipado (parcial, pareado com S1)**
- Trocar `catch (error: any)` → `unknown` + narrowing tipado (helper
  `isHttpError(e)`). Sem regressão de comportamento (mesmos ramos 409/429).

### Onda 2 — Resiliência de rede + observabilidade (P1)

**WP-S3 · Backoff, cap de retry e 429 com countdown**
- Fila de mutação: backoff exponencial + jitter, cap de retries (ex.: 3), com
  reconciliação via `refreshCart` no esgotamento (fail-loud, não fail-silent).
- 429: honrar `retry_after_seconds` com countdown visível (M:SS) e botão de retry;
  não martelar o backend. Reusa `operationalCopy` p/ mensagens.
- Sinal **offline**: listener `online`/`offline` + `visibilitychange` → refetch de
  dado stale ao voltar o foco; banner "Sem conexão — tentando de novo…"
  ([[feedback_transparent_timeouts]], omotenashi-first).
- **Idade do dado / staleness** no acompanhamento de pedido: "Atualizado há X"
  usando timestamp que a projection já expõe (sem prometer o que a API não cumpre).
- **Telemetria** (espelha Sentry opt-in do Django):
  - Client + BFF capturam erro não-tratado; envio opt-in via `NUXT_SENTRY_DSN`
    (à-prova-de-ausência: sem DSN, no-op) **ou** POST para nova rota Django
    `storefront/client-error/` que já flui ao Sentry existente — decidir no WP.
  - Nunca logar PII (telefone, endereço). Sanitização antes do envio.
- **Aceite:** testes simulam 429/503/timeout e verificam backoff + estado de erro
  visível; banner offline testado (component); staleness com teste de countdown;
  telemetria inerte sem DSN (teste).

### Onda 3 — Elegância & dívida (P2/P3)

**WP-S4-b · Dead code, type-safety & lint**
- Auditoria de componentes órfãos (grep de import-count nos 238; listar graveyard;
  remover com segurança ou justificar retenção). Sem remoção às cegas.
- Reduzir `any` defensivo (`normalizeSubstitutes`, Google Maps) para `unknown` +
  type guards onde viável.
- `npm run lint` verde no repo inteiro; corrigir achados.
- **Aceite:** lista de graveyard documentada; lint verde; nenhum `any` novo introduzido.

**WP-S5 · E2E de fluxos críticos (Playwright)**
- menu → PDP → carrinho (optimistic + 409 substitute) → checkout → tracking.
- Guard de `/conta/*` (redirect p/ login sem sessão).
- 429/offline: degradação visível (não tela branca).
- **Aceite:** ≥4 specs e2e verdes contra `nuxt preview` + Django de teste;
  documentado como rodar (`npm run test:e2e`).

**WP-S6 · Component tests (jsdom) dos componentes de risco**
- `CartQuantityAction`, `SubstituteSheet`, `AddressPicker`, `StockNotifyButton`,
  skeleton/loading states.
- **Aceite:** render + interação + estados de erro/pending cobertos.

---

## Sequência sugerida

```
S0 (foundation) → S1 ∥ S2 (test-first estado/BFF, + S4-a) → S3 (resiliência+telemetria)
   → S6 (component) ∥ S4-b (dead code/lint) → S5 (e2e) → arquivar
```

## Gate de cada WP
1. Baseline verde antes de começar.
2. Teste que falha reproduz o gap.
3. Fix → `npm run test` (unit+component) verde + `npm run lint` limpo.
4. `npm run build` sem erro de tipo.
5. Commit atômico por WP; nada de resíduo ([[feedback_zero_residuals]]).

## Fora de escopo (registrar, não fazer aqui)
- PWA/service worker offline real (só sinal de conexão nesta onda).
- Responsive images/CDN transforms.
- SSR payload cache / stale-while-revalidate.
