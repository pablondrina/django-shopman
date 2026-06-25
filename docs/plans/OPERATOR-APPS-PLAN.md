# OPERATOR-APPS-PLAN — Operador em apps dedicados, Admin encolhido

> Decisão arquitetural do Pablo (2026-06-25): cada superfície operacional vira app
> Nuxt/UI-Thing dedicado, headless, no seu subdomínio; o Django Admin recua para
> CRUD + Configurações com acesso super-restrito. Constrói sobre
> [SURFACE-CONVERGENCE-PLAN](SURFACE-CONVERGENCE-PLAN.md) (mesmo princípio: um sistema
> canônico por superfície) e os ADRs de superfície headless
> ([adr-012](../decisions/adr-012-headless-surface-contract.md),
> [adr-013](../decisions/adr-013-pos-offline-policy-and-surface-ownership.md),
> [adr-014](../decisions/adr-014-surface-data-presentation-cut.md)).

## Estado-alvo — mapa de subdomínios (Nelson)

| Subdomínio público | Superfície | Stack | Estado hoje |
|---|---|---|---|
| `staging.` (apex) | Loja | Nuxt `storefront-uithing-nuxt` | ✅ no ar |
| `pos.` | PDV | Nuxt `pos-uithing-nuxt` | ✅ no ar |
| `kds.` | KDS | Nuxt `kds-uithing-nuxt` | ✅ no ar |
| **`gestor.`** | **Gestor de Pedidos** | **Nuxt `orders-uithing-nuxt` (NOVO)** | ❌ hoje é tela Admin |
| **`fournil.`** | **Produção / Chão de Fábrica** | Nuxt (fase posterior) | ❌ hoje Admin + HTMX |
| `admin.` | Django Admin (CRUD + Config) | Unfold | em `api.…/admin/`, acesso amplo |
| `api.` | API/BFF interno | Django REST | ✅ no ar |

**Princípio de nomenclatura (desacoplar nome interno do subdomínio público).** O
subdomínio de operador é interno (sem SEO/bookmark público) → barato renomear depois.
Portanto: o nome de código é **estável e neutro pela função da tela** (segue
`pos-uithing-nuxt`/`kds-uithing-nuxt`); `gestor.`/`fournil.` são SÓ o domínio público.
A string de cada host vive num **único lugar** (settings/env/spec DO), nunca literal
espalhado — trocar `fournil.→forno.` no futuro = editar 1 valor.

## Decisões travadas (Pablo, 2026-06-25)

1. **Nome da surface de pedidos:** `surfaces/orders-uithing-nuxt` (função, não persona,
   coerente com pos/kds).
2. **Gate de permissão do Gestor:** `backstage.operate_orders` (família operador, como
   `operate_pos`/`operate_kds`, concedida via grupos/PIN do doorman). Gestão de pedido é
   tarefa de chão, uso diário. Implica **criar `can_operate_orders()`** e **migrar o
   console + a API** para esse gate (hoje o console usa `shop.manage_orders` e a API
   referencia `backstage.operate_orders`, que **não existe** — ver Gap-1).
3. **Form factor do Gestor:** desktop-first **mas responsivo** (board lado a lado no
   desktop; degrada bem em tablet/celular — o dono acompanha pedidos pelo telefone).
4. **Contexto doctl:** renomear `fix` → `shopman-staging-deploy` (housekeeping, WP-0).

### Decisões adiadas (confirmar quando a fase chegar — aprovação por etapa)

- **Fase 3** — modelo de restrição do `admin.` (IP allowlist? 2FA obrigatório? ambos?).
- **Fase 4** — o que migra para `fournil.` (avanço de passo ao vivo no chão) vs o que
  fica CRUD no Admin (planejamento/relatórios de produção).

## Achados da análise (estado real do código)

A análise reversa mostrou que **a Fase 1 está muito mais adiantada do que o WP supôs**:

- **A API headless de pedidos já existe** em `shopman/backstage/api/operations.py` e
  está roteada em `shopman/backstage/api/urls.py:69-75`:
  - Leitura: `OrderQueueView` (`GET orders/`, two-zone), `OrderDetailView`
    (`GET orders/<ref>/`).
  - Escrita: `OrderAdvanceView`, `OrderConfirmView`, `OrderRejectView`,
    `OrderCancelView` — **todas reusam `shopman/backstage/services/orders.py` →
    `shopman/shop/services/operator_orders.py`** (mesma cadeia do console; zero regra
    duplicada, Core respeitado).
- **As projeções de pedido são read-only e reaproveitáveis** —
  `shopman/backstage/projections/order_queue.py`: `build_two_zone_queue()`,
  `build_operator_order()`, `build_order_card()` (dataclasses, serializadas por
  `shopman/backstage/api/projections.py:projection_data`).
- **A fundação Nuxt é copiável** — `surfaces/pos-uithing-nuxt` e `kds-uithing-nuxt`
  compartilham `app/components/Ui/` (51 componentes), tokens em
  `app/assets/css/tailwind.css`, o proxy Django em `server/utils/djangoProxy.ts` +
  `server/api/v1/[...path].ts`, `useOperatorLock.ts`, e o setup vitest da camada
  `presentation/` pura.

### Gaps que a Fase 1 precisa fechar

- **Gap-1 (permissão dangling):** `backstage.operate_orders` é referenciada por 4 views
  da API (`operations.py:341,360,374`) mas **não é declarada em nenhum
  `Meta.permissions`/migração nem concedida a grupo** → hoje **só superuser** acessa
  `/api/v1/backstage/orders/*`. O console, por sua vez, gateia em `shop.manage_orders`
  via `can_manage_orders()`. Inconsistência a resolver (decisão 2).
- **Gap-2 (paridade de ações):** a API **não cobre** 3 ações do console:
  `settle_delivery_cash` (acerto dinheiro entrega), `requeue_fiscal` (reprocessar NFC-e),
  `save_internal_notes`. Precisam de endpoints novos reusando
  `shopman/backstage/services/orders.py`.
- **Gap-3 (alertas sem API):** `OperatorAlert` é **HTMX-only** (`views/alerts.py`); não
  há `/api/v1/backstage/alerts/`. O Gestor é o consumidor natural do painel de alertas →
  a API de alertas precede o kill do HTMX de alertas (Fase 2).

---

## FASE 0 — Housekeeping

### WP-0 · Renomear contexto doctl `fix` → `shopman-staging-deploy` · ✅ CONCLUÍDO
- Chave do auth-context renomeada no config do doctl (tokens preservados).
- Referências no repo atualizadas (restava só `SURFACE-CONVERGENCE-PLAN.md`).
- Verificado: `doctl --context shopman-staging-deploy apps get 40b86e35-…` responde.
- **Pendente (memória):** atualizar `project_pos_staging_deploy` quando voltar ao deploy.

---

## FASE 1 — Gestor de Pedidos como app Nuxt (`gestor.` / `orders-uithing-nuxt`)

> A API e as projeções já existem; o trabalho é **fechar os gaps**, **construir a
> surface** e **fazer o cutover** tirando o console de pedidos do Admin.

### WP-G1 · Completar a API headless de pedidos + permissão canônica · ✅ CONCLUÍDO
> Feito (commit `15700620`): gate reconciliado p/ `shop.manage_orders` (a dangling
> `backstage.operate_orders` foi removida; `manage_orders` já existe + é concedida a
> Caixa/Gerente, então o operador de balcão já tem acesso — sem migração nem churn no
> Core); 3 endpoints novos (`settle-delivery-cash`, `requeue-fiscal`, `notes`) reusando o
> facade `backstage/services/orders.py`; teste de contrato `test_api_orders_surface.py`
> (10 casos). `make` backstage (555) + lint verdes.
**Backend, sem Nuxt ainda. Não tocar o Core (`packages/`) — reusar services do orquestrador.**

1. **Permissão `operate_orders` (fecha Gap-1):**
   - Declarar `("operate_orders", "Pode operar a gestão de pedidos …")` em
     `Meta.permissions` de um model do app `backstage` (espelhar `operate_kds` em
     `shopman/backstage/models/kds.py:92`; escolher o model âncora coerente —
     recomendado: junto dos demais gates de operação). + migração.
   - Adicionar `can_operate_orders(user)` em `shopman/backstage/permissions.py`
     (`is_superuser(user) or user.has_perm("backstage.operate_orders")`).
   - Conceder em `shopman/shop/management/commands/setup_groups.py` e
     `migrations/0008_setup_default_groups.py` ao(s) grupo(s) de operador certos.
   - Migrar o **console** (`admin_console/orders.py`) e a **API** para
     `can_operate_orders` (a API troca a string `required_permission` por algo
     consistente; idealmente passar a checar via predicado). Incluir `operate_orders`
     em `can_view_operator_alerts`.
2. **Endpoints faltantes (fecha Gap-2)** em `operations.py` + rotas em `api/urls.py`,
   reusando `shopman/backstage/services/orders.py`:
   - `POST orders/<ref>/settle-delivery-cash/` → `settle_delivery_cash(...)`.
   - `POST orders/<ref>/requeue-fiscal/` → `requeue_fiscal_emission(...)`.
   - `POST orders/<ref>/notes/` → `save_internal_notes(...)` (e/ou `PUT` no detail).
3. **Testes:** migrar/espelhar a cobertura de ação do console para testes de API em
   `shopman/backstage/tests/` (confirm/advance/reject/cancel/settle/requeue/notes +
   gate 403 sem `operate_orders`, 200 com). Documentar quaisquer chaves novas de
   `Order.data` em [docs/reference/data-schemas.md](../reference/data-schemas.md) (as
   atuais — `payment`, `internal_notes` — já existem; verificar).
- **Aceite:** `make test` verde; `/api/v1/backstage/orders/*` cobre 100% das ações do
  console; operador com `operate_orders` (não-superuser) acessa; sem `operate_orders` → 403.

### WP-G2 · Scaffold `surfaces/orders-uithing-nuxt` + telas · ✅ CONCLUÍDO
> Feito (commits `8a0a9907` + fix de lock): surface criada da fundação POS/KDS;
> camada `presentation/` pura testada (vitest 12); board Entrada/Preparo/Saída
> desktop-first responsivo + detalhe; `npm ci`/build/dev verdes. Gotcha resolvido:
> o lock gerado por npm 11.5.1 omitia `commander@11.1.0` aninhado sob svgo →
> regerado a partir do lock em-sync do kds-uithing.
**Copiar a fundação do POS/KDS e parametrizar (ver checklist em
[SURFACE-CONVERGENCE-PLAN](SURFACE-CONVERGENCE-PLAN.md) + análise).**
1. **Copiar as-is:** `app/components/Ui/`, `app/assets/css/tailwind.css`,
   `server/utils/djangoProxy.ts`, `server/api/v1/[...path].ts`,
   `composables/useOperatorLock.ts`, `vitest.config.ts`, `tsconfig.json`,
   `ui-thing.config.ts`.
2. **Parametrizar:** `package.json` (name `orders-uithing-nuxt`, porta dev **3004**),
   `nuxt.config.ts` (`colorMode.storageKey`, `app.baseURL` ← `NUXT_APP_BASE_URL`,
   título, `NUXT_ORDERS_LOGIN_NEXT_PATH`), favicon.
3. **Camada `presentation/` pura (vitest):** view de card de pedido, board de duas zonas
   (Entrada/Preparo/Saída), detalhe, e resolução de affordances de ação
   (confirmar/avançar/rejeitar/cancelar/acerto-dinheiro/reprocessar-fiscal/notas) a
   partir da projeção — espelhando `presentation/` do POS. Tipos em
   `app/types/orders.ts` a partir das projeções do Django.
4. **Telas (desktop-first, responsivo):** fila/board de pedidos (polling/SSE como o KDS),
   detalhe do pedido com timeline + notas, ações com confirmação. Idioma neutro das
   surfaces; acessibilidade/omotenashi first-class (heading grande, contraste, pt-BR).
5. **Lock de operador:** reusar `useOperatorLock` (PIN doorman) como PDV/KDS.
- **Aceite:** `npm run test` (vitest) verde na `presentation/`; app sobe em
  `127.0.0.1:3004` consumindo `api.` local; console limpo; POSTs 200.

### WP-G3 · Deploy staging + verificação AO VIVO · ✅ CONCLUÍDO
> Feito (deploy `6ba69687` ACTIVE, 2026-06-25): spec do DO editado ADITIVAMENTE —
> componente `orders-uithing` (mirror do kds), domínio ALIAS
> `gestor.staging.nelsonboulangerie.com.br`, ingress rule ANTES do catch-all da loja;
> 12 secrets `EV[...]` preservados. **Nenhuma mudança em ALLOWED_HOSTS/CSRF/CORS foi
> necessária** — o proxy Nuxt reescreve Host/Origin p/ `api.staging` (mesmo padrão de
> pos/kds). **Verificação AO VIVO autenticada (full stack):** `gestor.staging/` serve o
> app (200, shell "Gestor de Pedidos", chunk `orders-uithing`); leitura autenticada via
> proxy `GET /api/v1/backstage/orders/` → 200 com dados reais (25 pedidos ativos);
> escrita via proxy (notes POST, CSRF auto pelo proxy) → 200, persistiu, revertido.
> Gate `manage_orders` confirmado. 1º deploy falhou por lock npm fora de sync (ver WP-G2).

### WP-G3b · Cutover (repointar nav + aposentar o console) → BUNDLE com Fase 2
> **Decisão de sequenciamento (2026-06-25):** a remoção do console **não é um delete
> simples** — reescreve o gate de browser-QA omotenashi (`_order_queue_check`,
> `_late_payment_after_cancel_check`, `_ifood_stale_check` em `services/omotenashi_qa.py`
> apontam p/ URLs do console), os gates de a11y (`test_a11y_dynamic`/`_keyboard`) e o
> shell legado `gestor/base.html` — **exatamente os gates que a Fase 2 (kill-legacy-HTMX)
> derruba**. Removê-lo agora obrigaria a religar esses gates DUAS vezes. Então: o app
> Gestor já é o primário vivo em `gestor.staging`; o console fica como fallback inofensivo
> e a remoção (nav→`SHOPMAN_ORDERS_BASE_URL`, delete de `admin_console/orders.py` +
> rotas + templates + repoint do QA/a11y) entra na Fase 2, num passo coerente único.

### WP-G3 (original) · Deploy staging + cutover (aposentar o console de pedidos)
1. **Deploy aditivo** no app DO `shopman-staging` (`40b86e35-…`), via
   `--context shopman-staging-deploy` (AUTODEPLOY DESLIGADO):
   - Editar o spec (preservar secrets `EV[...]`): novo componente Nuxt service (build
     `npm ci && npm run build`, run `node .output/server/index.mjs`, `http_port 3000`,
     `source_dir /surfaces/orders-uithing-nuxt`, envs
     `NUXT_DJANGO_BASE_URL=https://api.staging…` + `NUXT_APP_BASE_URL=/`), domain ALIAS
     `gestor.staging.nelsonboulangerie.com.br` na zona gerenciada, ingress rule ANTES do
     catch-all da loja.
   - Atualizar Django `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` (e CORS se aplicável) para o
     host `gestor.…` — **a string do host num único lugar** (settings via env).
2. **Verificar AO VIVO** (`gestor.staging…`): board carrega, todas as ações executam
   contra a API, lock de operador funciona, paridade com o console confirmada.
3. **Só então aposentar o console de pedidos** (padrão WP1, não delete cego):
   - Remover `shopman/backstage/admin_console/orders.py` + as rotas em `config/urls.py`
     (`admin_console_orders*`) + templates `admin_console/` de pedidos + link no nav do
     Admin (a string do host do Gestor sai de settings, oculto se vazio — como o POS fez
     em `f175c6b6`).
   - Migrar/triar os testes do console que ainda fizerem sentido (a cobertura de ação já
     migrou no WP-G1); remover testes órfãos de view; zero residuals.
- **Aceite:** `gestor.staging…` no ar e verificado; console de pedidos removido; `make
  test`/`make admin`/`make lint` verdes; nenhum `NoReverseMatch`/link morto.

---

## FASE 2 — Matar os legados Django/HTMX do operador (padrão WP1)

> Regra dura: as views HTMX são harness de teste. ANTES de deletar, **caracterizar e
> migrar cobertura** (redundante→deletar, único→migrar p/ teste de API/projeção) e
> **confirmar paridade Nuxt AO VIVO**. Caracterização já feita (ver análise): 14 testes
> quebram na deleção (todos têm endpoint de API equivalente → migrar p/ teste de API);
> 32 testes de projeção/serviço sobrevivem; 16 testes só-de-template morrem com o template.

### WP-K1 · API de `OperatorAlert` + consumo no Gestor (fecha Gap-3, pré-requisito) · ✅ CONCLUÍDO + DEPLOYADO + VERIFICADO
> Feito (commit `1b14b2cb`, deploy `1ee0a83c` ACTIVE): `GET /api/v1/backstage/alerts/` +
> `POST .../<pk>/ack/` reusando `services/alerts.py`; gate `CanViewOperatorAlerts`
> (predicado canônico); 6 testes de contrato. Consumo no Gestor: `useAlerts` + `AlertsBell`
> (sino+badge+painel ack) no header. Verificado AO VIVO: alerts API via proxy → 200, 42
> alertas ativos (1 crítico) com dados reais. **Paridade do KDS Nuxt confirmada AO VIVO**
> (index/board/customer board → 200 com dados reais) — pré-condição p/ matar o KDS-HTMX.

### WP-K1 (original) · API de `OperatorAlert` + consumo no Gestor (fecha Gap-3, pré-requisito)
- Criar `GET /api/v1/backstage/alerts/` (lista + contagem) e
  `POST /api/v1/backstage/alerts/<pk>/ack/`, reusando
  `shopman/backstage/services/alerts.py`; gate `can_view_operator_alerts`.
- Consumir o painel/badge de alertas na surface `orders-uithing-nuxt` (o hub do operador
  é a casa natural dos alertas).
- Testes de API espelhando os do serviço.
- **Aceite:** alertas visíveis no Gestor ao vivo; API testada.

### WP-K2/K3 + cutover · ✅ EXECUTADO (commit `c96b02db`, deploy `cfffee75`)
> Teardown único e coeso (arquivos compartilhados: urls/nav/omotenashi/base.html/gate
> canônico). **KDS-HTMX**: views/templates/rotas removidos; cobertura migrada p/
> `test_api_kds_surface.py` (9). **Alertas-HTMX**: views/partials/rotas removidos (API
> WP-K1 + sino do Gestor + changelist Admin cobrem). **Console de pedidos**: removido;
> nav "Pedidos"/"KDS"/"POS" → apps Nuxt via `SHOPMAN_*_BASE_URL` (oculto se vazio;
> settings + spec staging setados). **Bug real corrigido** (achado na migração de testes):
> `confirm_order` não envolvia `InvalidTransition`→`OrderError` → API confirmava com 500.
> Gates omotenashi-QA/a11y das telas Django retiradas removidos (browser-QA Nuxt =
> follow-up); superfície Unfold `admin-console-orders` removida, projeções re-registradas
> sob exceção `headless-operator-api`. RBAC/confirm/locust repointados p/ a API.
> `make test` 2099 + `make admin` 245 + ruff verdes. `gestor/base.html` fica (Produção
> usa até Fase 4). **✅ VERIFICADO AO VIVO** (deploy `cfffee75` ACTIVE): legados
> `/admin/operacao/pedidos/`, `/operacao/kds/`, `/operacao/kds/cliente/`,
> `/gestor/alertas/badge/` → 404; `/gestor/producao/kds/` → 200 (Produção intacta);
> gestor./kds. apps + orders/alerts API → 200; nav do Admin linka gestor./kds./pos.

### WP-K2 (original) · Matar o KDS-HTMX (station + customer board)
- Confirmar paridade AO VIVO em `kds.staging…` (estação write/SSE/expedição + board do
  cliente `/retirada`).
- Migrar os ~14 testes view-specific de `kds_station`/`kds_customer` para testes da API
  `/api/v1/backstage/kds/*` (endpoints já existem). Deletar templates `runtime/kds_*`,
  views `kds_station.py`/`kds_customer.py`, rotas em `urls.py`, links de nav. Remover
  testes só-de-template (`test_kds_audio`, partes de `test_a11y_*`).
- **Aceite:** rotas `/operacao/kds/*` fora; `make test`/`make admin`/`make lint` verdes;
  KDS Nuxt segue íntegro ao vivo; zero residuals.

### WP-K3 · Matar o HTMX de alertas (depende de WP-K1)
- Deletar `views/alerts.py`, templates `gestor/partials/alerts_*`, rotas; alertas agora
  servidos pela API + Gestor.
- **Aceite:** sem rotas `/gestor/alertas/*`; alertas ao vivo no Gestor; testes verdes.

> **Nota:** `views/production.py` (`/gestor/producao/kds/*`) **NÃO** morre na Fase 2 — seu
> destino é a Fase 4 (`fournil.`). Fica vivo até lá.

---

## FASE 3 — Encolher o Admin/Unfold + faxina

> Admin = só CRUD + Configurações, acesso super-restrito. Tudo sob o **Unfold Canonical
> Gate** (`make admin`).

### WP-A1 · Restrição de acesso ao `admin.` — 2FA · ✅ IMPLEMENTADO + DEPLOYADO + VERIFICADO (gated OFF), deploy `d4002b49`
> **Verificado AO VIVO** (deploy ACTIVE): `/ready/` 200, `/admin/` 200 (flag OFF → sem
> gate, otp tables migradas no release sem quebrar boot), changelist de produtos 200,
> `/admin/2fa/verify/` 200, apps+API de operador 200. 2FA fica OFF até enrollment.
>
> **Achado pré-existente (NÃO regressão; tarefa separada):** `/admin/orderman/order/`
> 500 no staging — `TemplateDoesNotExist: orderman/admin/order_change_list.html`. Causa:
> `packages/*` não declaram `package-data`, então `pip install ./packages/orderman`
> (Dockerfile) não embarca `templates/`. Local é editável (mascara). Predata esta sessão
> (não toquei orderman). Fix de packaging spawnado como tarefa própria.
> Feito (commit `c58c3f4e`): infra de 2FA TOTP **atrás da flag `SHOPMAN_ADMIN_REQUIRE_2FA`
> (default OFF)** — no staging fica OFF até o enrollment (ligar tranca fora). `make test`
> 2109 + `make admin` 247 + ruff verdes; fluxo ponta-a-ponta testado LOCAL (8 testes:
> gate off→in, on→redirect, verify c/ token válido→in, etc.). Design implementado:
> django_otp+otp_totp, OTPMiddleware, `AdminTwoFactorMiddleware`, view+template
> `two_factor/verify.html`, command `setup_admin_totp`. Migrações do django-otp aplicam
> no release (job roda migrate). **PARA LIGAR (atendido):** (1) `setup_admin_totp <user>`
> p/ cada superuser (escaneia o QR), (2) setar `SHOPMAN_ADMIN_REQUIRE_2FA=true` no spec +
> redeploy, (3) logar com token. **PROD:** + IP allowlist no ingress do admin.

#### Design (referência — já implementado)

**Design (django-otp, compat Django 6.0 confirmada — `django-otp>=1.7,<2.0`):**
1. `pyproject.toml`: + `django-otp`. `INSTALLED_APPS` += `django_otp`,
   `django_otp.plugins.otp_totp`. `MIDDLEWARE`: + `django_otp.middleware.OTPMiddleware`
   logo após `AuthenticationMiddleware`. Migração do django-otp.
2. Flag `SHOPMAN_ADMIN_REQUIRE_2FA` (env, **default False** → staging segue acessível
   até o enrollment; liga-se quando o Pablo enrola o device).
3. Middleware-gate `AdminTwoFactorMiddleware`: em paths `/admin/`, se flag ON +
   autenticado + `not request.user.is_verified()` → redirect p/ a view de verificação
   (exceto a própria view + logout, p/ não criar loop).
4. View + template (Unfold-styled, `admin/base.html`) de entrada de token TOTP.
5. Enrollment: management command `setup_admin_totp <user>` → cria `TOTPDevice`
   confirmado e imprime o `otpauth://` URI (sem UI custom p/ enrollment).
6. Testes do gate: flag OFF → admin 200; flag ON + sem device → redirect; flag ON +
   verificado → 200. Verificação ponta-a-ponta LOCAL (liga flag, enrola, gera TOTP),
   nunca no staging (lockout).
7. Docs (`docs/`) + **follow-up PROD: IP allowlist** (middleware/edge no `admin.`,
   quando o admin tiver ingress próprio e IP fixo/VPN — fora do staging).

### WP-A2 · Faxina canônica · ✅ JÁ SATISFEITA
> O sidebar já é benchmark (BACKOFFICE-UNFOLD-REVISION + ADMIN-CONFIG-OMOTENASHI) e o
> "encolher" aconteceu na Fase 2 (console de pedidos removido; nav env-gated p/ os apps
> Nuxt; admin carrega 200, sem links mortos). Não há cruft seguro a remover — reorganizar
> um sidebar-benchmark especulativamente degradaria. Nada a fazer agora.

---

## FASE 4 — Produção / Chão de Fábrica (`fournil.`) — fase posterior, escopo separado

> Persona = Craftsman (WorkOrders / produção em LOTE — NÃO confundir com prep de pedido
> do KDS). Já há Admin/Unfold (`/admin/operacao/producao/`) + HTMX
> `/gestor/producao/kds/`. **Decisão pendente** (Pablo): o que migra para `fournil.`
> (avanço de passo ao vivo no chão) vs o que fica CRUD no Admin
> (planejamento/relatórios). Escopar em plano próprio quando chegar. Só aqui morre o
> `views/production.py` HTMX (migrando seus testes de step/finish p/ a API
> `/api/v1/backstage/production/*`, que já existe).

---

## Deploy + verificação (resumo operacional)

- **App DO:** `shopman-staging`, id `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`, multi-componente.
- **Autodeploy DESLIGADO** (spec sem `deploy_on_push`): push no main NÃO deploya.
- **Contexto doctl:** `shopman-staging-deploy` (após WP-0; token full).
  - Deploy: `doctl --context shopman-staging-deploy apps create-deployment 40b86e35-…`
  - Monitorar: `… apps get-deployment <appid> <depid> --format Phase` até `ACTIVE`.
  - Novo componente/subdomínio: `apps spec get` → editar (ADITIVO, preservar `EV[...]`) →
    `apps update … --spec … --update-sources`.
- **Verificar código novo:** assinatura única da feature nos chunks `/_nuxt/*.js` servidos.
- **Gotchas:** Django cacheia `Shop.defaults` em memória (restart do componente p/
  refletir DB); preview de surfaces Nuxt navega por `127.0.0.1:<porta>`, nunca
  `localhost` (IPv6→426).

## Gates por WP

`make test`, `make admin` (sem `url` antes de PR), `make lint`, `vitest` nas surfaces
tocadas, e **verificação AO VIVO no staging** após deploy. Sem gambiarras; zero
residuals em renames/deleções; reusar services do orquestrador, nunca duplicar regra;
não tocar `packages/` (Core).

## Ordem de execução sugerida

WP-0 → **Fase 1** (G1 → G2 → G3) → **Fase 2** (K1 → K2 → K3) → **Fase 3** (A1 → A2) →
**Fase 4** (plano próprio). Aprovação do Pablo por etapa.
