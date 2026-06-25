# Kickoff — Fase 4: Produção / Chão de Fábrica como app Nuxt (`fournil.`)

> Prompt auto-contido para uma nova sessão. Cola o bloco abaixo. Continua a iniciativa
> "Operador em apps dedicados" (Fases 0–3 concluídas; ver `docs/plans/OPERATOR-APPS-PLAN.md`).

---

## Contexto
Monorepo django-shopman. Arquitetura headless: Django (orquestrador + API + Admin/Unfold)
em `api.staging.nelsonboulangerie.com.br`; superfícies ricas em Nuxt/UI-Thing (`surfaces/`),
cada uma no seu subdomínio. Tenant ativo = Nelson Boulangerie. **LEIA primeiro:** `CLAUDE.md`
(Estrutura, "Core é Sagrado", Admin/Unfold canonical), `docs/plans/OPERATOR-APPS-PLAN.md`
(toda a iniciativa, Fases 0–3 feitas), `.codex/skills/unfold-admin-canonical/SKILL.md`,
`docs/reference/glossary.md`. Convenções duras: nomes persona (Offerman/Stockman/Craftsman/
Orderman/Guestman/Doorman/Payman), `ref` não `code`, centavos `_q`, ZERO jargão inventado,
ZERO residuals em rename/deleção, ZERO aliases de compat, NÃO tocar `packages/` (Core) sem
entender como já resolve. Frontend: HTMX↔servidor, Alpine↔DOM (no Django); Nuxt/Vue nas surfaces.

## O que já foi entregue (Fases 0–3, deployadas + verificadas no staging)
- **Gestor de Pedidos** = app Nuxt dedicado `surfaces/orders-uithing-nuxt` (`gestor.`), sobre
  a API headless `api/v1/backstage/orders/*`. **É O TEMPLATE A COPIAR** nesta fase.
- **KDS** = `surfaces/kds-uithing-nuxt` (`kds.`); **POS** = `surfaces/pos-uithing-nuxt` (`pos.`).
- Legados HTMX de operador (KDS-HTMX, alertas-HTMX, console de pedidos) **aposentados**;
  cobertura migrada p/ testes de API. Nav do Admin linka os apps via `SHOPMAN_*_BASE_URL`
  (oculto se vazio). 2FA do Admin implementado (gated OFF). Packaging do Core corrigido
  (todos os `packages/*` agora embarcam `templates/` via `[tool.setuptools.package-data]`).
- **Padrão estabelecido por superfície:** (1) garantir/estender a API headless reusando os
  services do orquestrador (nunca duplicar regra); (2) copiar a fundação de uma surface Nuxt
  existente e parametrizar; (3) deploy aditivo no spec DO + verificação AO VIVO autenticada;
  (4) só então aposentar o legado (caracterizar→migrar cobertura→deletar→rewire gates).

## Tarefa desta fase — Produção/Chão de Fábrica vira app Nuxt dedicado
Persona = **Craftsman** (WorkOrders / produção em LOTE antecipada — **NÃO** confundir com o
prep de pedido do KDS; ver memória `feedback_production_vs_sales`). Hoje a produção tem DUAS
superfícies Django: (a) **console Admin/Unfold** `/admin/operacao/producao/*` (painel,
planejamento, matriz, fichas, relatórios, pesagem, compromissos) — **FICA** como CRUD/
planejamento/relatório; (b) **HTMX "KDS de produção"** `/gestor/producao/kds/*` (avanço de
passo ao vivo no chão, concluir WO) — **É O QUE MIGRA** para o app Nuxt `fournil.` e depois
morre. **A API já existe:** `api/v1/backstage/production/*`.

### Decisões a CONFIRMAR com o Pablo antes de executar (aprovação por etapa)
1. **Nome estável da surface.** Coerente com a convenção por-função (pos/kds/orders):
   recomendado `surfaces/production-uithing-nuxt`. (`fournil.` é só o domínio público; nunca
   hardcodar — vive no spec/env.) Persona alt.: `craftsman-uithing-nuxt`.
2. **Corte exato live vs CRUD.** Recomendado: vai pro `fournil.` o **chão ao vivo** = board
   de WorkOrders iniciadas + avanço de passo + concluir/quick-finish + void + atalhos de
   escassez de insumo. Fica no Admin: planejamento, matriz, fichas técnicas, relatórios,
   pesagem, compromissos, criação em lote. Confirmar.
3. **Form factor.** Chão de fábrica = provável tablet/touch-first (como o KDS), tema escuro?
   Confirmar (o KDS é dark-first; o Gestor é light-first/desktop). 
4. **Restrição/ingress** do `fournil.` (igual aos outros: subdomínio ALIAS + ingress antes do
   catch-all da loja). Gate de permissão: `craftsman.view_workorder` (read) / `change_workorder`
   (write) — já é o gate da API (ver `api/operations.py`).

### Passos (cada um com gates verdes; plano em `docs/plans/`)
1. **API headless de produção — completar se preciso.** Já existem (em
   `shopman/backstage/api/operations.py`, rotas em `shopman/backstage/api/urls.py:70-89`):
   `ProductionBoardView` (GET `production/`), `ProductionKDSView` (GET `production/kds/`),
   `WorkOrderAdvanceStepView` (POST `production/<wo_id>/advance-step/`),
   `WorkOrderQuickFinishView` (POST `production/quick-finish/`), `WorkOrderVoidView` (POST
   `production/<wo_id>/void/`). Gate: `craftsman.view_workorder`/`change_workorder`. Projeções:
   `shopman/backstage/projections/production.py` (`build_production_board`, `build_production_kds`).
   **A API de produção provavelmente NÃO tem teste de contrato** — escrever
   `shopman/backstage/tests/test_api_production_surface.py` (espelhar `test_api_kds_surface.py`:
   board/kds/advance-step/quick-finish/void + gate 403). Cobrir o que a paridade da tela exige
   (ex.: modais de escassez de insumo — ver `production_kds_finish_view`, que retorna
   `material_shortage`/`order_shortage`; garantir que a API expõe esse erro estruturado).
2. **Scaffold `surfaces/production-uithing-nuxt`** copiando `orders-uithing-nuxt` (fundação:
   `app/components/Ui/`, `server/utils/djangoProxy.ts`, `server/api/v1/[...path].ts`,
   `app/utils/api.ts`, `useOperatorLock.ts`, vitest/ts config). Parametrizar: `package.json`
   (name + porta dev **3005**), `nuxt.config.ts` (`colorMode`, `app.baseURL` ← `NUXT_APP_BASE_URL`,
   título, `NUXT_PRODUCTION_LOGIN_NEXT_PATH`). Camada `presentation/` pura testada (vitest):
   board de WO, card de WO (passo atual/progresso), affordances (avançar passo/concluir/void).
   Telas: board do chão + detalhe/passo. Lock de operador (PIN doorman).
   **GOTCHA do lockfile:** o `package-lock.json` gerado por npm 11.x local omite deps aninhadas
   (ex.: `commander`), quebrando `npm ci` no buildpack do DO. Gere o lock a partir de uma
   surface que já buildou (copie o de `orders-/kds-uithing-nuxt` e troque o nome) e confirme
   `npm ci` limpo ANTES de deployar.
3. **Deploy aditivo + verificação AO VIVO** (ver "Deploy" abaixo). Domínio
   `fournil.staging.nelsonboulangerie.com.br`. Setar `SHOPMAN_PRODUCTION_BASE_URL` no spec +
   `settings.py` (espelhar `SHOPMAN_ORDERS_BASE_URL`/`SHOPMAN_KDS_BASE_URL` — já existem) e o nav
   do Admin (`shopman/backstage/admin/navigation.py`, item "Produção ao vivo" env-gated, como
   POS/KDS/Gestor). Verificar autenticado: board/advance/finish via proxy → 200, gate.
4. **Só então matar o HTMX "KDS de produção" (padrão WP1, não delete cego):**
   - **⚠️ SUTILEZA:** `shopman/backstage/views/production.py` tem helpers COMPARTILHADOS
     (`handle_production_post`, `render_production_surface`, `production_redirect`,
     `_selected_date`, `_report_filters`, etc.) usados pelo **console Admin que FICA**
     (`admin_console/production.py` importa esses). NÃO delete o módulo inteiro — remova SÓ as
     4 views HTMX do KDS: `production_kds_view`, `production_kds_cards_view`,
     `production_kds_finish_view`, `production_advance_step_view` (+ helpers exclusivos delas),
     mantendo os compartilhados.
   - Rotas `gestor/producao/kds/*` em `shopman/backstage/urls.py:30-33`.
   - Templates `shopman/backstage/templates/gestor/producao/` (kds.html + partials).
   - **`gestor/base.html` + `gestor/404.html` MORREM** (produção é o último consumidor do shell
     legado). O `handler404 = "shopman.backstage.views.errors.custom_404"` (config/urls.py)
     renderiza `gestor/404.html` → reavaliar (apontar p/ um 404 simples ou remover o handler
     custom). Conferir `shopman/backstage/operator/context.py` (build_operator_context) e o
     context processor do shell — podem virar dead code.
   - Migrar cobertura: testes que tocam as views HTMX → testes da API
     (`test_production_kds_steps`, `test_production_operational`, partes de `test_backstage_e2e`).
     Manter os testes de PROJEÇÃO/serviço (`build_production_kds`, `apply_advance_step`).
   - Rewire de gates: `omotenashi_qa.py` (`_production_kds_check` linha ~114/232 → dropar ou
     repointar p/ Nuxt, como fiz com os outros); a11y (`test_a11y_dynamic::test_a11y_producao_kds`,
     e `test_a11y_keyboard` — que na Fase 2 eu reapontei o skip-link/nav-landmark p/
     `backstage:production_kds`; como o shell gestor morre, esses testes saem de vez);
     `test_a11y_backstage_baseline` (`order_shortage.html` etc.); canonical gate
     (`scripts/check_unfold_canonical.py`: remover/ajustar as surfaces `runtime-production-kds`
     e `runtime-operator-shell`); `locustfile.py` (já repointei produção p/ API na Fase 2 —
     conferir). `make admin` tem que passar.
   - Confirmar paridade `fournil.staging` AO VIVO antes de deletar. Zero residuals.

## Deploy + verificação no staging (AUTODEPLOY DESLIGADO)
App DO: `shopman-staging`, id `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`. Contexto doctl válido =
**`shopman-staging-deploy`** (token full). Deploy de código (spec inalterado):
`doctl --context shopman-staging-deploy apps create-deployment 40b86e35-…`. Monitorar
`apps get-deployment <appid> <depid> --format Phase` até `ACTIVE` (~10-20min; build
multi-componente). **Novo componente/subdomínio:** `apps spec get … > /tmp/spec.yaml` → editar
ADITIVO (componente Nuxt service: build `npm ci && npm run build`, run `node .output/server/
index.mjs`, http_port 3000, `source_dir /surfaces/production-uithing-nuxt`, envs
`NUXT_DJANGO_BASE_URL=https://api.staging…` + `NUXT_APP_BASE_URL=/`; + domain ALIAS
`fournil.staging…` na zona gerenciada; + ingress rule ANTES do catch-all da loja; + env
`SHOPMAN_PRODUCTION_BASE_URL` no bloco global) → `apps update 40b86e35-… --spec /tmp/spec.yaml
--update-sources`. **PRESERVAR os secrets `EV[...]` do spec live.** Nuxt proxia p/ `api.`
(reescreve Host/Origin) → NÃO precisa mexer em ALLOWED_HOSTS/CSRF p/ o novo subdomínio.
Verificação autenticada por curl: logar em `api.staging/admin/login/` (user `pablo`, senha em
`~/.shopman/shopman-staging-admin-2026-05-06.txt`), pegar `sessionid`, e GET/POST nos endpoints
via o proxy `fournil.staging/api/v1/backstage/production/*`.

## Processo e gates
Análise primeiro → escreva/atualize o plano em `docs/plans/` → fatie em WPs auto-contidos com
aprovação do Pablo por etapa (confirmar as 4 decisões acima). Por WP: `make test`, `make admin`
(sem `url` antes de PR), `make lint`, `vitest` nas surfaces tocadas, e verificação AO VIVO no
staging após deploy. Trabalhar em branch (`git checkout -b feat/fase4-producao`); commitar por
WP; mergear no `main` antes de cada deploy (o spec builda do `main`). Gotchas: Django cacheia
`Shop.defaults` em memória (restart do componente p/ refletir DB); preview de surfaces Nuxt
navega por `127.0.0.1:<porta>`, nunca `localhost` (IPv6→426). Memória-chave:
`project_operator_apps_plan`, `project_pos_staging_deploy`, `feedback_production_vs_sales`,
`feedback_respect_core_no_reinvent`.
