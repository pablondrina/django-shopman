# CLAUDE.md — Django Shopman

Instruções para agentes de código que trabalham neste repositório.

## Estrutura do Projeto

```
packages/               8 apps pip-instaláveis (sem dependência entre si)
├── utils/              Utilitários compartilhados (monetary, phone, admin)          [shopman-utils]
├── offerman/           Catálogo: produtos, preços, listings, coleções, bundles      [shopman-offerman]
├── stockman/           Estoque: quants, moves, holds, posições, alertas, planejamento [shopman-stockman]
├── craftsman/          Produção: receitas, work orders, BOM, sugestão               [shopman-craftsman]
├── orderman/           Pedidos: sessions, orders, channels, directives, fulfillment [shopman-orderman]
├── guestman/           Clientes: customers, contatos, grupos, loyalty, RFM          [shopman-guestman]
├── doorman/            Auth: OTP, device trust, bridge tokens, magic links          [shopman-doorman]
└── payman/             Pagamentos: intents, transactions, service                   [shopman-payman]

shopman/                Namespace package (PEP 420) — sem __init__.py
└── shop/               Orquestrador (app Django, name="shopman.shop", label="shop")  [django-shopman]
    ├── lifecycle.py    dispatch() — coordenação config-driven por ChannelConfig
    ├── production_lifecycle.py  dispatch_production() — lifecycle de WorkOrders
    ├── services/       services (availability, alternatives, stock, payment, customer, checkout, pricing, etc.)
    ├── adapters/       adapters (stock, payment_efi, payment_stripe, notification_*, etc.)
    ├── rules/          engine.py, pricing.py, validation.py — regras configuráveis via admin
    ├── models/         Shop, Promotion, Coupon, RuleConfig, OperatorAlert, KDS*, DayClosing
    ├── handlers/       directive handlers (notification, fulfillment, fiscal, loyalty, returns, etc.)
    ├── setup.py        register_all() — registro centralizado de handlers
    ├── config.py       ChannelConfig dataclass (8 aspectos)
    ├── protocols.py    Contratos (NotificationBackend, CustomerBackend, etc. — Stock é módulo)
    ├── topics.py       Constantes de tópicos de directives
    ├── notifications.py Registry + dispatch de notificações
    ├── confirmation.py Helpers de confirmação
    ├── modifiers.py    D1, Discount, Employee, HappyHour modifiers
    ├── webhooks/       efi.py, stripe.py
    ├── admin/          shop, orders, alerts, kds, closing, rules, dashboard, widgets
    ├── web/            Storefront (Django templates + HTMX)
    │   ├── views/      19 módulos (catalog, cart, checkout, tracking, auth, kds, pedidos, pos, etc.)
    │   ├── cart.py     CartService
    │   ├── urls.py     Todas as URLs
    │   └── templates/  78 templates (storefront, kds, pedidos, pos, components)
    ├── api/            API REST (DRF) — views, serializers, catalog, account, tracking
    ├── context_processors.py  shop() + cart_count()
    ├── middleware.py   ChannelParamMiddleware, OnboardingMiddleware
    ├── management/commands/   seed, cleanup_d1, cleanup_stale_sessions, suggest_production
    ├── apps.py         ShopmanConfig (signal wiring + handler registration + rules boot)
    └── tests/          7 test modules + web/ + integration/ + e2e/

config/                 Django project wrapper (settings.py, urls.py, wsgi.py, asgi.py)
manage.py               Django management entrypoint (repo root)
pyproject.toml          Build + test config (repo root)

instances/              Instâncias Django (não são pip packages)
└── nelson/             Nelson Boulangerie (futuro repo shopman-nelson)
```

### Conceitos Primários

- **Lifecycle** (`lifecycle.py`): Coordenação de lifecycle. Signal `order_changed` → `dispatch(order, phase)` → services. Comportamento 100% config-driven via `ChannelConfig` — sem classes de Flow.
- **Services** (`services/`): Lógica de negócio. Cada service usa Core services (StockService, PaymentService, CatalogService, etc.) via adapters.
- **Adapters** (`adapters/`): Swappable via settings. `get_adapter("payment", method="pix")` → `payment_efi`.
- **Rules** (`rules/`): Regras configuráveis via admin com `RuleConfig` no DB. Engine avalia rules ativas por contexto.

## Convenções Ativas

- **`ref` not `code`**: Identificadores textuais são `ref`. Exceções deliberadas: `Product.sku`, `Recipe.code` (SlugField descritivo, ex: `croissant-v1`), `WorkOrder.code` (código sequencial auto-gerado, ex: `WO-001`).
- **Centavos com `_q`**: Valores monetários são inteiros em centavos, sufixo `_q`. Ex: `price_q = 1500` → R$ 15,00.
- **Confirmação otimista**: Pedido auto-confirma se operador não cancela dentro do prazo.
- **Zero residuals em renames**: Ao renomear, zerar TUDO (variáveis, strings, comments, docstrings). Nada de `# formerly X`.
- **Zero backward-compat aliases**: Projeto novo, do zero. Não há consumidores externos. Nunca criar aliases tipo `OldName = NewName`. Apagar o nome antigo completamente.
- **Offerman = somente produtos vendáveis**: Insumos ficam em Stockman/Craftsman, nunca no Offerman.
- **Frontend: HTMX ↔ servidor, Alpine.js ↔ DOM**:
  - **HTMX**: toda comunicação com servidor (GET, POST, polling, swaps). Incluindo `hx-on::before-request`/`after-request` para estados visuais de loading atrelados a requests.
  - **Alpine.js**: todo estado local na tela (abrir/fechar, toggles, dropdowns, modals, steppers, validação client-side, contadores, masks).
  - **NUNCA**: `onclick="..."`, `onchange="..."`, `document.getElementById`, `classList.toggle/add/remove` em templates. Usar `@click`, `x-show`, `x-data`, `x-text`, `$store`.
  - **Exceção**: IntersectionObserver e APIs do browser que não têm equivalente Alpine (geolocation, clipboard, service worker).

## Como Rodar

```bash
make test              # Todos os testes (~2.448: cores + orquestrador)
make test-offerman     # Apenas offerman (offering)
make test-stockman     # Apenas stockman (stocking)
make test-framework    # Orquestrador + integration + e2e
make lint              # Ruff
make run               # Dev server (localhost:8000)
make seed              # Popular banco com dados Nelson Boulangerie
make migrate           # Migrações
```

## Core é Sagrado — Regras de Integridade

O `packages/` é um conjunto de 8 apps pip-instaláveis, muito bem desenhado, robusto e flexível.
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
- **Não deixar resíduos** em renames (migrações serão resetadas no projeto novo).
- **Não assumir problemas** sem consultar ADRs e estado atual do projeto.

## Referências

- [docs/reference/data-schemas.md](docs/reference/data-schemas.md) — **Obrigatório**: inventário de chaves em Session.data, Order.data, Directive.payload
- [docs/guides/lifecycle.md](docs/guides/lifecycle.md) — Guia da arquitetura: Lifecycle, Services, Adapters, Rules
- [PRODUCTION-PLAN.md](PRODUCTION-PLAN.md) — Plano de produção: WP-F0 a WP-F18 (UX, operação, canais, governance)
- [EVOLUTION-PLAN.md](EVOLUTION-PLAN.md) — Plano completo: WP-E1 a WP-E6 (disponibilidade, loyalty, cartão, dashboard, notificações, API)
- [docs/ROADMAP.md](docs/ROADMAP.md) — Visão geral de próximos passos e ideias futuras
- [docs/](docs/README.md) — Documentação completa (guias, ADRs, referência técnica)
- [docs/reference/glossary.md](docs/reference/glossary.md) — Glossário de termos de domínio

### Planos Completos (arquivo)

Todos os planos de execução foram concluídos e arquivados em `docs/plans/completed/`:
- REFACTOR-PLAN (WP-0 a WP-R5), CONSOLIDATION-PLAN (C1-C6),
  HARDENING-PLAN (H0-H5), BRIDGE-PLAN (B1-B7), RESTRUCTURE-PLAN, WORKPACKAGES,
  RESTRUCTURE-APP-PLAN (WP-R0 a WP-R9)
