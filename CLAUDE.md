# CLAUDE.md — Django Shopman

Instruções para agentes de código que trabalham neste repositório.

## Estrutura do Projeto

```
packages/               11 apps pip-instaláveis (sem dependência entre si)
├── utils/              Utilitários compartilhados (monetary, phone, admin)          [shopman-utils]
├── refs/               Registro de refs tipadas, rename/audit e campos reutilizáveis [shopman-refs]
├── offerman/           Catálogo: produtos, preços, listings, coleções, bundles      [shopman-offerman]
├── stockman/           Estoque: quants, moves, holds, posições, alertas, planejamento [shopman-stockman]
├── craftsman/          Produção: receitas, work orders, BOM, sugestão               [shopman-craftsman]
├── orderman/           Pedidos: sessions, orders, channels, directives, fulfillment [shopman-orderman]
├── guestman/           Clientes: customers, contatos, grupos, loyalty, RFM          [shopman-guestman]
├── doorman/            Auth: OTP, device trust, bridge tokens, magic links          [shopman-doorman]
├── payman/             Pagamentos: intents, transactions, service                   [shopman-payman]
├── buyman/             Compras: fornecedores, materiais, custos (procurement, Fase 1) [shopman-buyman]
└── fiscalman/          Fiscal: classificação NFC-e (schema em Product.metadata)      [shopman-fiscalman]

shopman/                Namespace package (PEP 420) — sem __init__.py
├── shop/               Orquestrador (app Django, label="shop") — health/readiness views [django-shopman]
│   ├── lifecycle.py    dispatch() — coordenação config-driven por ChannelConfig
│   ├── production_lifecycle.py  dispatch_production() — lifecycle de WorkOrders
│   ├── services/       services de orquestração (availability, cancellation, stock, payment, customer, etc.)
│   ├── adapters/       adapters swappable (stock, payment_efi, payment_stripe, notification_*, etc.)
│   ├── rules/          engine.py, pricing.py, validation.py — regras configuráveis via admin
│   ├── models/         Shop, Channel, RuleConfig, NotificationTemplate, OmotenashiCopy
│   ├── handlers/       directive handlers (notification, fulfillment, fiscal, loyalty, returns, etc.)
│   ├── config.py       ChannelConfig dataclass (8 aspectos)
│   ├── protocols.py    Contratos (NotificationBackend, CustomerBackend, etc.)
│   ├── notifications.py Registry + dispatch de notificações
│   ├── modifiers.py    D1, Discount, Employee, HappyHour modifiers
│   ├── webhooks/       efi.py, stripe.py, ifood.py
│   ├── admin/          admin registrations dos models de shop
│   ├── projections/    types.py (shared projection types — Availability, OrderItem, etc.)
│   ├── views/          health.py — /health/ e /ready/
│   ├── middleware.py   AppPlatformHealthCheckHost, APIVersionHeader, OperatorSessionDomain
│   ├── management/commands/   seed, cleanup_d1, cleanup_stale_sessions, maintenance_worker, sweep_stuck_orders, ifood_poll
│   ├── apps.py         ShopmanConfig (signal wiring + handler registration + rules boot)
│   └── tests/          lifecycle, services, adapters, handlers, integration, e2e
│
├── storefront/         Superfície customer HEADLESS (app Django, label="storefront")
│   ├── api/            endpoints JSON consumidos pelo BFF do app Nuxt (cart, checkout, auth, tracking, account, catalog…)
│   ├── presentation/   projections puras (home, cart, checkout, order_tracking, payment, account…)
│   ├── intents/        interpretação server-side de ações (cart set-qty, phone, auth)
│   ├── services/       checkout, checkout_defaults, pickup_slots, ifood_*
│   ├── models/         Promotion, Coupon, DeliveryZone
│   ├── middleware.py   ChannelParamMiddleware (captura ?channel=)
│   ├── urls.py         montado em /api/v1/ (o app cliente é surfaces/storefront-nuxt)
│   └── tests/          api, projections, checkout, rate-limiting, delivery zones
│
└── backstage/          Superfícies operador HEADLESS + Admin/Unfold (app Django, label="backstage")
    ├── api/            endpoints JSON dos apps operador Nuxt (pos, kds, production, orders, closing, operator)
    ├── projections/    kds, order_queue, pos, closing, production, dashboard
    ├── services/       operator, closing, production, cash
    ├── models/         KDSInstance, KDSTicket, DayClosing, OperatorAlert, CashRegister*
    ├── admin_console/  telas Admin/Unfold (produção, fechamento)
    ├── middleware.py   OnboardingMiddleware
    ├── urls.py         montado em /api/v1/backstage/ + SSE /gestor/events/ (os apps são surfaces/*-nuxt)
    └── tests/          POS, KDS, produção, fechamento, contratos de superfície, e2e

surfaces/               5 apps Nuxt 4 (SSR) — as superfícies vivas em produção
├── storefront-nuxt/   loja do cliente (apex, mobile-first)  → api.
├── pos-nuxt/          PDV (desktop-first)                   → api./backstage
├── kds-nuxt/          cozinha (KDS)                         → api./backstage
├── orders-nuxt/       gestor de pedidos                     → api./backstage
└── production-nuxt/   produção/fornadas (kiosk Solari)      → api./backstage
    Cada app: BFF Nitro (server/utils/djangoProxy.ts, CSRF), composables + presentation/ pura (vitest).

config/                 Django project wrapper + deployment app
├── settings.py, urls.py, wsgi.py, asgi.py
└── management/commands/ seed.py — bootstrap de dados do deployment (Nelson)
manage.py               Django management entrypoint (repo root)
pyproject.toml          Build + test config (repo root)
```

> **Cutover headless:** os apps Django `storefront`/`backstage` NÃO renderizam mais
> HTML — servem API JSON + projections. As superfícies são os 5 apps Nuxt em
> `surfaces/`, que falam com o Django via BFF (cookie de sessão cross-subdomínio
> `.boulangerie`). A seção "Frontend: HTMX ↔ Alpine" abaixo vale só para as telas
> Admin/Unfold que ainda são Django-rendered.

> **Tenant = config + dados + marca, zero código.** Não há pacote Python de
> instância. "Nelson" é o `Shop` singleton + dados no DB (`Channel`/`RuleConfig`/
> `OmotenashiCopy`/catálogo via `seed`) + marca (assets do storefront) + settings
> do deployment. O `seed` vive no app `config`; pricing (D-1/Happy Hour) e a
> estratégia de balcão são genéricos no orquestrador, dirigidos por `RuleConfig`.

### Regra de Dependência (3 apps)

```
storefront ──imports──→ shop ←──imports── backstage
     ↓                   ↓                    ↓
  (never)            packages/            (never)
                   ↗  ↑  ↑  ↖
          offerman stockman orderman craftsman ...
```

### Conceitos Primários

- **Lifecycle** (`lifecycle.py`): Coordenação de lifecycle. Signal `order_changed` → `dispatch(order, phase)` → services. Comportamento 100% config-driven via `ChannelConfig` — sem classes de lifecycle ou herança Python.
- **Services** (`services/`): Lógica de negócio. Cada service usa Core services (StockService, PaymentService, CatalogService, etc.) via adapters.
- **Adapters** (`adapters/`): Swappable via settings. `get_adapter("payment", method="pix")` → `payment_efi`.
- **Rules** (`rules/`): Regras configuráveis via admin com `RuleConfig` no DB. Engine avalia rules ativas por contexto.

### Integração entre apps — signal vs adapter vs directive

Cores nunca se importam. Para causar efeito em outro app, a **interação decide** a ferramenta (lei: [ADR-001](docs/decisions/adr-001-protocol-adapter.md), exemplos: [guia lifecycle](docs/guides/lifecycle.md)):

- **Anunciar evento, sem esperar retorno** (consumir estoque ao finalizar produção, notificar) → **signal**; handler numa ponte `<core>/contrib/<alvo>/` (point-to-point) ou no shop (multi-app). Ex.: `production_changed` → `craftsman/contrib/stockman` escreve o ledger direto (`kind=MAKE`) — único escritor.
- **Precisar de retorno síncrono / sequenciar** (reservar estoque e saber se deu; capturar pagamento antes da baixa) → **adapter/Protocol** via settings, **só com 2+ impls reais** (nunca "para o futuro").
- **Comando async confiável** (retry/idempotência) → **Directive** ([ADR-003](docs/decisions/adr-003-directives-sem-celery.md)).
- ⚠️ Nunca criar backend de **escrita** plugável quando um signal basta (foi a dívida do `InventoryProtocol` morto). Seam dormente só se já tem consumidores reais + dono/prazo (ex.: `INVENTORY_BACKEND` leitura → Buyman WP-B5b; **não ligar** antes de insumo ter estoque, senão `adjust`/`finish` bloqueiam).

## Convenções Ativas

- **`ref` not `code`**: Identificadores textuais são `ref`. Exceções deliberadas: `Product.sku`, `WorkOrder.code` (código sequencial auto-gerado, ex: `WO-001`).
- **Centavos com `_q`**: Valores monetários são inteiros em centavos, sufixo `_q`. Ex: `price_q = 1500` → R$ 15,00.
- **Confirmação otimista**: Pedido auto-confirma se operador não cancela dentro do prazo.
- **Zero residuals em renames**: Ao renomear, zerar TUDO (variáveis, strings, comments, docstrings). Nada de `# formerly X`. ⚠️ **Vale até o go-live.** A partir do `git tag go-live-v1`, renames seguem expand-contract — ver [ADR-015](docs/decisions/adr-015-backward-compat-policy-post-prod.md) e [production-upgrades.md](docs/guides/production-upgrades.md).
- **Zero backward-compat aliases**: Projeto novo, do zero. Não há consumidores externos. Nunca criar aliases tipo `OldName = NewName`. Apagar o nome antigo completamente. ⚠️ **Vale até o go-live.** Depois, aliases temporários são permitidos em janela explícita (1 sprint) com `# DEPRECATED(remove in v{version})` — ver [ADR-015](docs/decisions/adr-015-backward-compat-policy-post-prod.md).
- **Offerman = somente produtos vendáveis**: Insumos ficam em Stockman/Craftsman, nunca no Offerman.
- **Frontend: HTMX ↔ servidor, Alpine.js ↔ DOM**:
  - **HTMX**: toda comunicação com servidor (GET, POST, polling, swaps). Incluindo `hx-on::before-request`/`after-request` para estados visuais de loading atrelados a requests.
  - **Alpine.js**: todo estado local na tela (abrir/fechar, toggles, dropdowns, modals, steppers, validação client-side, contadores, masks).
  - **NUNCA**: `onclick="..."`, `onchange="..."`, `document.getElementById`, `classList.toggle/add/remove` em templates. Usar `@click`, `x-show`, `x-data`, `x-text`, `$store`.
  - **Exceção**: IntersectionObserver e APIs do browser que não têm equivalente Alpine (geolocation, clipboard, service worker).
- **Tempo real por SSE (cross-surface, site-wide)**: sempre que houver estado que muda no servidor e importa na tela (acompanhamento, estoque, verificação, KDS, badges), preferir **push por SSE** em vez de depender de polling. O SSE é camada de push sobre um **fetch canônico** que continua sendo a fonte da verdade (no evento, refaça o fetch REST); o **poll fica só como fallback** em cadência calma. Canais nomeados + permissão no `ShopmanChannelManager`, proxy same-origin no BFF via `server/utils/eventStream.ts` (`proxyEventStream`). Ver [ADR-016](docs/decisions/adr-016-sse-first-realtime.md).

## Admin/Unfold — Regra de Canonicidade

Telas operacionais dentro do Admin usam o **Unfold Canonical Gate**. Backstage novo deve nascer em
Admin/Unfold por padrão; POS e Storefront são exceções explícitas. Antes de criar ou alterar
`admin_console`, `shopman/backstage/admin/`, `contrib/admin_unfold` ou templates Admin de pacotes,
leia:

- `.codex/skills/unfold-admin-canonical/SKILL.md`
- `docs/engineering/unfold_admin_page_playbook.md`
- `docs/engineering/unfold_canonical_policy.md`
- `docs/reference/unfold_canonical_inventory.md`

Regra curta: **widget/helper/componente canônico > classes copiadas**. Se existe primitiva Unfold,
use a primitiva. Copiar classes do Unfold nao basta, porque perde markup, JS, acessibilidade,
overflow, espaçamento e comportamento futuro.

Componentes Unfold devem ser chamados com `{% component "unfold/components/..." %}`; incluir
`unfold/components/...` diretamente e bypass. Links/paragrafos visuais em templates Admin usam
`unfold/components/link.html` e `unfold/components/text.html`.

Modal em pagina custom so pode usar o wrapper aprovado `admin_console/unfold/modal.html`, que espelha
os tokens do shell modal/command do Unfold instalado. Nao crie overlay novo.

Pagina Admin custom deve seguir o contrato oficial do Unfold (`UnfoldModelAdminViewMixin`,
`TemplateView`, `title`, `permission_required`, `.as_view(model_admin=...)`), estender
`admin/base.html`, e consumir uma projection registrada em `shopman/backstage/projections/`.
O gate tambem conhece superficies legado: elas podem existir, mas nao podem crescer silenciosamente.

No fluxo dev, rode sempre pelo Makefile:

```bash
make admin
```

Esse unico comando cobre gate canônico, auditoria estrita, contrato de superficies/projections,
versao instalada do `django-unfold` e testes de integração Admin/Unfold. O gate falha se a versao
instalada divergir do inventario oficial local.

Para iterar em uma tela especifica sem bloquear por divida nao relacionada, use o mesmo comando com
URL relativa:

```bash
make admin url=/admin/operacao/producao/
```

Esse escopo e para desenvolvimento local. Antes de PR, rode `make admin` sem `url`.

## Como Rodar

```bash
make test              # Todos os testes (~2.448: cores + orquestrador)
make test-offerman     # Apenas offerman (offering)
make test-stockman     # Apenas stockman (stocking)
make test-framework    # Orquestrador + integration + e2e
make admin             # Tudo de Admin/Unfold
make admin url=/admin/operacao/producao/  # Escopo local por URL Admin
make lint              # Ruff + Admin/Unfold
make run               # Dev server (localhost:8000)
make seed              # Popular banco com dados Nelson Boulangerie
make migrate           # Migrações
```

## Core é Sagrado — Regras de Integridade

O `packages/` é um conjunto de 11 apps pip-instaláveis, muito bem desenhado, robusto e flexível.
Antes de alterar qualquer coisa no Core, **compreenda como ele já resolve o problema**.

1. **Não adicionar campos a modelos do Core sem necessidade comprovada.** Os modelos `Session`, `Order`,
   `Channel`, `Directive` já possuem `JSONField` (`data`, `config`, `payload`, `snapshot`) projetados
   para extensibilidade sem migrações. Se a informação é contextual, use o JSON. Se é estrutural e
   queryable em escala, aí sim discuta um campo.

2. **Não criar migrações no Core para dados contextuais.** `origin_channel`, `delivery_address`,
   `coupon_code`, `payment` — tudo isso vive em `Session.data` / `Order.data` / `Directive.payload`.
   Esse é o padrão do projeto. Siga-o.

3. **Consultar a referência de schemas antes de escrever em JSONFields.** O inventário completo de
   chaves usadas em `Session.data`, `Order.data` e `Directive.payload` está documentado em
   [`docs/reference/data-schemas.md`](docs/reference/data-schemas.md). Adicione novas chaves lá
   antes de usá-las.

4. **Confiar no Core, desconfiar da sua compreensão.** Se parece que o Core não suporta algo, é mais
   provável que você não tenha encontrado onde ele já resolve. Leia os services (`commit.py`,
   `modify.py`, `write.py`), os handlers, e os testes antes de propor mudanças.

5. **O `CommitService` é o contrato Session→Order.** Ele copia chaves específicas de `session.data`
   para `order.data`. Para propagar uma nova chave, adicione-a na lista explícita em `_do_commit()`.
   Não invente fluxos paralelos.

## O Que NÃO Fazer

- **Não alterar os packages do Core sem entender como eles já funcionam** — leia services, handlers, e testes primeiro.
- **Não inventar features** durante migração ou refatoração.
- **Não usar jargão inventado** — nomes devem ser descritivos e auto-explicativos.
- **Não deixar resíduos** em renames (migrações serão resetadas no projeto novo). ⚠️ Até o go-live; depois migrations são append-only — ver [ADR-015](docs/decisions/adr-015-backward-compat-policy-post-prod.md).
- **Não assumir problemas** sem consultar ADRs e estado atual do projeto.

## Referências

- [docs/reference/data-schemas.md](docs/reference/data-schemas.md) — **Obrigatório**: inventário de chaves em Session.data, Order.data, Directive.payload
- [docs/guides/lifecycle.md](docs/guides/lifecycle.md) — Guia da arquitetura: Lifecycle, Services, Adapters, Rules
- [docs/ROADMAP.md](docs/ROADMAP.md) — Visão geral de próximos passos e ideias futuras
- [docs/plans/WP-GAP-07-pre-prod-migration-playbook.md](docs/plans/WP-GAP-07-pre-prod-migration-playbook.md) — Playbook ativo de migração/pré-prod
- [docs/plans/PROJECTION-UI-PLAN.md](docs/plans/PROJECTION-UI-PLAN.md) — Plano ativo de projections/UI
- [docs/](docs/README.md) — Documentação completa (guias, ADRs, referência técnica)
- [docs/reference/glossary.md](docs/reference/glossary.md) — Glossário de termos de domínio

### Planos Completos (arquivo)

Todos os planos de execução foram concluídos e arquivados em `docs/plans/completed/`:
- REFACTOR-PLAN (WP-0 a WP-R5), CONSOLIDATION-PLAN (C1-C6),
  HARDENING-PLAN (H0-H5), BRIDGE-PLAN (B1-B7), RESTRUCTURE-PLAN, WORKPACKAGES,
  RESTRUCTURE-APP-PLAN (WP-R0 a WP-R9)
