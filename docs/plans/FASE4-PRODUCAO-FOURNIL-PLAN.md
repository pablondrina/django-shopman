# FASE4-PRODUCAO-FOURNIL-PLAN — Produção / Chão de Fábrica como app Nuxt (`fournil.`)

> Plano ativo. Continua a iniciativa "Operador em apps dedicados"
> ([OPERATOR-APPS-PLAN](OPERATOR-APPS-PLAN.md), Fases 0–3 concluídas). Kickoff de origem:
> [FASE4-PRODUCAO-FOURNIL-KICKOFF](FASE4-PRODUCAO-FOURNIL-KICKOFF.md).
> Persona = **Craftsman** (WorkOrders / produção em LOTE antecipada — **NÃO** confundir com
> o prep de pedido do KDS; ver memória `feedback_production_vs_sales`).

## Decisões travadas (Pablo, 2026-06-25)

1. **Nome da surface:** `surfaces/production-uithing-nuxt` (por função, coerente com
   pos-/kds-/orders-uithing-nuxt). `fournil.` é só o domínio público — string num único
   lugar (settings/env/spec DO), nunca hardcodada.
2. **Corte live-vs-CRUD — Pablo expandiu além da recomendação do kickoff:** migram pro
   `fournil.` **o chão ao vivo E o planejamento**:
   - **Vai pro app:** board de WO iniciadas (KDS de produção) + avançar passo + concluir
     (finish com força/escassez) + quick-finish + void + **planejamento + matriz de
     produção + sugestões + escassez de insumo (modais estruturados)**.
   - **Fica no Admin/Unfold (CRUD + back-office):** fichas técnicas (receitas/BOM),
     relatórios (history/operator_productivity/recipe_waste + export CSV), pesagem,
     compromissos de ordem, criação em lote administrativa.
   - **O console Admin de produção (`admin_console/production.py`) NÃO morre** — é o
     consumidor canônico dos helpers compartilhados (`handle_production_post`,
     `render_production_surface`, `production_redirect`) e o lar do CRUD/back-office.
     Redundância app(touch)↔Admin(CRUD) em planejamento é intencional (mesma divisão
     operador-vs-back-office das outras superfícies). Só as **4 views HTMX do KDS** de
     produção morrem (têm substituto Nuxt).
3. **Form factor:** tablet/touch-first, **tema claro** (como o Gestor de Pedidos; alvos
   grandes de toque, mas claro — não dark como o KDS).
4. **Gate:** **criar `backstage.operate_production`** (família operador, como
   `operate_pos`/`operate_kds`), concedida via grupos/PIN doorman. Substitui o gate atual
   da API (`craftsman.view_workorder`/`change_workorder`) — espelha a resolução do Gap-1
   do Gestor, na direção de criar a perm. Read+write colapsam numa só perm (como
   `operate_kds`/`manage_orders`).

## Estado do código (análise reversa — 2026-06-25)

- **API headless já existe** em `shopman/backstage/api/operations.py` (rotas em
  `api/urls.py`), gateada hoje em `craftsman.view_workorder`/`change_workorder`:
  - `ProductionBoardView` (GET `production/`) → `build_production_board` (já projeta
    matrix/sugestões/queues planned/started/finished/recipes/positions — **leitura de
    planejamento E chão já coberta**).
  - `ProductionKDSView` (GET `production/kds/`) → `build_production_kds`.
  - `WorkOrderAdvanceStepView` (POST `production/<wo_id>/advance-step/`).
  - `WorkOrderQuickFinishView` (POST `production/quick-finish/`).
  - `WorkOrderVoidView` (POST `production/<wo_id>/void/`).
- **Facade de serviço completa** (`shopman/backstage/services/production.py`): `apply_planned`,
  `apply_start`, `apply_finish` (levanta `ProductionStockShortError`/`ProductionOrderShortError`
  estruturados), `apply_advance_step`, `apply_quick_finish`, `apply_void`, `apply_suggestions`
  (bulk_plan). Domínio fica no Core (`shopman/shop/services/production.py` + Craftsman) —
  **não tocar**.
- **Gaps de API a fechar (paridade de tela):**
  - **G-PROD-1 (ações faltantes):** a API NÃO expõe `apply_planned` (planejar/matriz),
    `apply_start` (iniciar WO), nem `apply_finish` (concluir WO STARTED com `force`). Só
    tem advance-step, quick-finish e void. Planejamento + finish exigem novos endpoints.
  - **G-PROD-2 (escassez estruturada):** `WorkOrderQuickFinishView`/`WorkOrderAdvanceStepView`
    só capturam `ProductionError` genérico → 400 `{"detail": ...}` plano. A tela HTMX
    expõe `material_shortage`/`order_shortage` (campos `missing`, `required`, `requested`,
    `order_refs`). A API precisa de um **envelope de erro estruturado** (código +
    payload) para o app reproduzir os modais de escassez.
  - **G-PROD-3 (permissão):** trocar o gate dos endpoints de produção de `craftsman.*`
    para `backstage.operate_production` (novo).
- **Sem teste de contrato de produção** — criar `test_api_production_surface.py`
  (espelhar `test_api_kds_surface.py`).

### Subtileza crítica (NÃO deletar o módulo inteiro)

`shopman/backstage/views/production.py` mistura **4 views HTMX do KDS** com **helpers
compartilhados** usados pelo console Admin que FICA:

- **Morrem (WP-P4):** `production_kds_view`, `production_kds_cards_view`,
  `production_kds_finish_view`, `production_advance_step_view` + constantes de template
  exclusivas (`KDS_TEMPLATE`, `KDS_PARTIAL_TEMPLATE`, e os `*_PARTIAL_TEMPLATE` de
  escassez se ninguém mais usar) + `_staff_required`/`_check_late_started_orders` se
  ficarem órfãos.
- **FICAM:** `handle_production_post`, `render_production_surface`, `production_redirect`,
  `_selected_date`, `_report_filters`, `_coerce_iso_date` — importados por
  `admin_console/production.py`.

---

## WP-P1 · API headless de produção completa + permissão `operate_production` · ⏳

**Backend, sem Nuxt. Reusar a facade `backstage/services/production.py`; NÃO tocar o Core
(`packages/`).**

1. **Permissão `operate_production` (fecha G-PROD-3):**
   - Declarar `("operate_production", "Pode operar a produção (chão + planejamento)")` em
     `Meta.permissions` do model âncora de operação do app `backstage` (espelhar
     `operate_kds`). + migração.
   - `can_operate_production(user)` em `shopman/backstage/permissions.py`
     (`is_superuser(user) or user.has_perm("backstage.operate_production")`).
   - Conceder em `shopman/shop/management/commands/setup_groups.py` +
     `migrations/0008_setup_default_groups.py` ao(s) grupo(s) de produção/operador certos
     (Produção/Gerente).
   - Rewire dos 5 endpoints de produção (board, kds, advance-step, quick-finish, void) +
     os novos (plan/start/finish) de `required_permission = "craftsman.*"` →
     `"backstage.operate_production"`.
2. **Endpoints faltantes (fecha G-PROD-1)** em `operations.py` + rotas em `api/urls.py`,
   reusando a facade:
   - `POST production/plan/` → `apply_planned(...)` (matriz/planejamento; aceita `force`,
     `source` suggested vs matrix). Captura `ProductionOrderShortError` → envelope.
   - `POST production/<wo_id>/start/` → `apply_start(...)`.
   - `POST production/<wo_id>/finish/` → `apply_finish(..., force)`. Captura
     `ProductionStockShortError` → envelope.
   - (Avaliar) `POST production/suggestions/apply/` → `apply_suggestions(bulk_plan)` se a
     tela de sugestões migrar; senão deferir.
3. **Envelope de escassez estruturado (fecha G-PROD-2):** padronizar o JSON de erro de
   escassez (espelhar o shape de erro do POS: `{"detail", "error": {"code", ...}}`):
   - `material_shortage`: `code="material_shortage"`, `missing=[{sku, needed, available,
     shortage}]`, `work_order_ref`.
   - `order_shortage`: `code="order_shortage"`, `work_order_ref`, `required`, `requested`,
     `order_refs`.
   - Aplicar em finish (novo), quick-finish (existente) e plan (order coverage).
4. **Teste de contrato** `shopman/backstage/tests/test_api_production_surface.py`
   (espelhar `test_api_kds_surface.py`): board/kds GET; plan/start/finish/advance-step/
   quick-finish/void POST; **gate 403 sem `operate_production`, 200 com**; **modais de
   escassez** (force=0 → 4xx com envelope estruturado; force=1 → 200). Migrar a cobertura
   de step/finish que hoje toca as views HTMX (`test_production_kds_steps`,
   `test_production_operational`) para a API. Manter testes de PROJEÇÃO/serviço
   (`build_production_kds`, `apply_advance_step`).
5. Documentar chaves novas relevantes em
   [docs/reference/data-schemas.md](../reference/data-schemas.md) se houver.

**Aceite:** `make test` + `make admin` + `make lint` verdes; `/api/v1/backstage/production/*`
cobre 100% das ações do chão + planejamento; operador com `operate_production` (não-superuser)
acessa, sem → 403; escassez retorna envelope estruturado.

## WP-P2 · Scaffold `surfaces/production-uithing-nuxt` + telas · ⏳

Copiar a fundação de `orders-uithing-nuxt` (mais próxima: touch + light) e parametrizar.

1. **Copiar as-is:** `app/components/Ui/`, `app/assets/css/tailwind.css`,
   `server/utils/djangoProxy.ts`, `server/api/v1/[...path].ts`,
   `composables/useOperatorLock.ts`, `vitest.config.ts`, `tsconfig.json`,
   `ui-thing.config.ts`.
2. **Parametrizar:** `package.json` (name `production-uithing-nuxt`, **porta dev 3005**),
   `nuxt.config.ts` (`colorMode` light, `app.baseURL` ← `NUXT_APP_BASE_URL`, título,
   `NUXT_PRODUCTION_LOGIN_NEXT_PATH`), favicon.
   - **GOTCHA do lockfile:** gerar `package-lock.json` a partir de uma surface que já
     buildou (copiar o de `orders-`/`kds-uithing-nuxt`, trocar o name) e confirmar
     `npm ci` limpo ANTES de deployar (npm 11.x local omite deps aninhadas → quebra DO).
3. **Camada `presentation/` pura (vitest):** board do chão (cards de WO: passo atual/
   progresso, affordances avançar/concluir/void), board de planejamento/matriz (células
   editáveis, sugestões), resolução de affordances a partir da projeção. Tipos em
   `app/types/production.ts` a partir das projeções do Django.
4. **Telas (tablet/touch-first, light):** (a) **Chão ao vivo** — board de WO iniciadas com
   avançar passo/concluir/void + modais de escassez; (b) **Planejamento** — matriz +
   sugestões + planejar/iniciar. Polling/SSE como o KDS. Acessibilidade/omotenashi
   first-class.
5. **Lock de operador:** reusar `useOperatorLock` (PIN doorman) como PDV/KDS.

**Aceite:** `vitest` verde na `presentation/`; app sobe em `127.0.0.1:3005` consumindo
`api.` local; console limpo; POSTs 200; modais de escassez funcionam.

## WP-P3 · Deploy staging + verificação AO VIVO · ⏳

1. **Deploy aditivo** no app DO `shopman-staging` (`40b86e35-…`), `--context
   shopman-staging-deploy` (AUTODEPLOY OFF):
   - `apps spec get` → editar ADITIVO (preservar secrets `EV[...]`): componente Nuxt
     service (build `npm ci && npm run build`, run `node .output/server/index.mjs`,
     `http_port 3000`, `source_dir /surfaces/production-uithing-nuxt`, envs
     `NUXT_DJANGO_BASE_URL=https://api.staging…` + `NUXT_APP_BASE_URL=/`); domain ALIAS
     `fournil.staging.nelsonboulangerie.com.br`; ingress rule ANTES do catch-all da loja;
     `SHOPMAN_PRODUCTION_BASE_URL` no bloco global.
   - `apps update … --spec … --update-sources`. O proxy Nuxt reescreve Host/Origin p/
     `api.` → sem mexer em ALLOWED_HOSTS/CSRF.
2. **Settings + nav Admin:** `SHOPMAN_PRODUCTION_BASE_URL` em `config/settings.py`
   (espelhar `SHOPMAN_ORDERS_BASE_URL`/`SHOPMAN_KDS_BASE_URL`); item "Produção ao vivo"
   env-gated no nav (`shopman/backstage/admin/navigation.py`), oculto se vazio.
3. **Verificar AO VIVO autenticado** (login `pablo`, senha em `~/.shopman/…`): board/kds
   via proxy `fournil.staging/api/v1/backstage/production/*` → 200; plan/start/advance/
   finish/void → 200; gate (sem perm → 403); escassez → envelope.

**Aceite:** `fournil.staging…` no ar e verificado; nav linka; paridade com o HTMX
confirmada AO VIVO.

## WP-P4 · Aposentar o HTMX "KDS de produção" (padrão WP1, não delete cego) · ⏳

Só após paridade AO VIVO confirmada no WP-P3.

1. **Remover SÓ as 4 views HTMX do KDS** de `views/production.py` (ver subtileza acima) +
   constantes/helpers exclusivos; **manter os helpers compartilhados**.
2. Rotas `gestor/producao/kds/*` em `shopman/backstage/urls.py`.
3. Templates `shopman/backstage/templates/gestor/producao/` (kds.html + partials).
4. **`gestor/base.html` + `gestor/404.html` MORREM** (produção é o último consumidor do
   shell legado). `handler404 = "shopman.backstage.views.errors.custom_404"`
   (config/urls.py) renderiza `gestor/404.html` → reapontar p/ 404 simples ou remover o
   handler custom. Conferir `shopman/backstage/operator/context.py`
   (`build_operator_context`) + context processor do shell → dead code.
5. **Migrar cobertura:** testes que tocam as views HTMX → testes de API (WP-P1 já cobre o
   grosso); remover testes só-de-template; manter projeção/serviço.
6. **Rewire de gates:** `services/omotenashi_qa.py` (`_production_kds_check`); a11y
   (`test_a11y_dynamic::test_a11y_producao_kds`, `test_a11y_keyboard` — skip-link/nav
   reapontado p/ `backstage:production_kds` na Fase 2 → sai de vez com o shell);
   `test_a11y_backstage_baseline` (`order_shortage.html` etc.); canonical
   (`scripts/check_unfold_canonical.py`: surfaces `runtime-production-kds` +
   `runtime-operator-shell`); `locustfile.py`. `make admin` tem que passar.
7. Zero residuals. Confirmar paridade AO VIVO antes de deletar.

**Aceite:** rotas `gestor/producao/kds/*` fora; `make test`/`make admin`/`make lint`
verdes; app `fournil.` íntegro AO VIVO; sem `NoReverseMatch`/link morto; shell `gestor/`
totalmente removido.

---

## Deploy + gates (resumo)

- App DO `shopman-staging` `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`; `--context
  shopman-staging-deploy`; AUTODEPLOY OFF; porta dev surface = **3005**; domínio
  `fournil.staging.nelsonboulangerie.com.br`.
- Por WP: `make test`, `make admin` (sem `url` antes de PR), `make lint`, `vitest` nas
  surfaces tocadas, verificação AO VIVO após deploy. Branch `feat/fase4-producao`; commit
  por WP; mergear no `main` antes de deploy (spec builda do `main`).
- Gotchas: Django cacheia `Shop.defaults` (restart do componente); preview Nuxt navega por
  `127.0.0.1:3005`, nunca `localhost` (IPv6→426).
