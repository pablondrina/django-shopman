# Django Shopman

![Python](https://img.shields.io/badge/python-≥3.12-blue)
![Django](https://img.shields.io/badge/django-≥5.2-green)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Release](https://img.shields.io/github/v/release/pablondrina/django-shopman?include_prereleases&label=release)
![Tests](https://img.shields.io/badge/tests-~1.900-brightgreen)

Django Shopman é um framework de commerce operations para pequenos negócios com operação física e remota — padarias, confeitarias, cafés, food service. Não é um e-commerce genérico; é uma base opinativa e modular para casos operacionais densos: catálogo com produção própria, estoque vivo, múltiplos canais (balcão, web, WhatsApp, marketplace), KDS, e gestão integrada.

Construído com Django 5.2+, arquitetura Protocol/Adapter, e foco em simplicidade operacional.

## Ecossistema

O Shopman é composto por **3 camadas**:

| Camada | Pip package | Descrição |
|--------|-------------|-----------|
| **Framework** | `django-shopman` | Orquestrador que integra os core apps via Lifecycles, Services e Adapters |
| **Core Apps** | `shopman-*` | 9 pacotes pip independentes, cada um com domínio próprio |
| **Instância** | — | Configuração específica do negócio (ex: Nelson Boulangerie) |

### Core Apps

Cada app é um pacote pip independente. Comunicação entre apps via `typing.Protocol` — zero imports diretos.

| App | Pip Package | Namespace | Domínio | Modelos Principais |
|-----|-------------|-----------|---------|-------------------|
| **Utils** | `shopman-utils` | `shopman.utils` | Monetário, formatting, phone | — |
| **Refs** | `shopman-refs` | `shopman.refs` | Referências tipadas | RefType, RefRecord |
| **Offerman** | `shopman-offerman` | `shopman.offerman` | Catálogo de produtos | Product, Listing, Collection, Bundle |
| **Stockman** | `shopman-stockman` | `shopman.stockman` | Estoque físico | Quant, Move, Hold, Position, Batch |
| **Craftsman** | `shopman-craftsman` | `shopman.craftsman` | Produção e receitas | Recipe, WorkOrder, WorkOrderItem |
| **Orderman** | `shopman-orderman` | `shopman.orderman` | Pedidos omnichannel | Session, Order, Directive, Channel |
| **Guestman** | `shopman-guestman` | `shopman.guestman` | CRM e clientes | Customer, ContactPoint, CustomerGroup |
| **Doorman** | `shopman-doorman` | `shopman.doorman` | Auth e acesso | VerificationCode, TrustedDevice, AccessLink |
| **Payman** | `shopman-payman` | `shopman.payman` | Pagamentos | PaymentIntent, PaymentTransaction |

## Quickstart

```bash
# 1. Clonar, subir Postgres+Redis via docker, instalar deps
git clone https://github.com/pablondrina/django-shopman.git
cd django-shopman
cp .env.example .env
make up           # docker compose: postgres:16-alpine + redis:7-alpine
make install

# 2. Criar banco e popular com dados demo (Nelson Boulangerie)
make migrate
make seed

# 3. Subir servidor
make run
# → http://localhost:8000/        (storefront)
# → http://localhost:8000/admin/  (admin — admin/admin)
# → http://localhost:8000/gestor/pedidos/ (gestor de pedidos)
# → http://localhost:8000/gestor/kds/     (kitchen display)
```

> Postgres é o default de dev — casa com os testes de concorrência do Stockman
> (`select_for_update`). Sem Docker? Deixe `DATABASE_URL` comentado no `.env` e o
> settings cai no fallback SQLite (mas os testes de concorrência serão pulados).
> Redis também faz parte do default: cache compartilhado, rate limit e SSE
> multi-worker. Sem Docker, deixe `REDIS_URL` comentado para fallback local leve.
> Detalhes em [`docs/getting-started/quickstart.md`](docs/getting-started/quickstart.md).

## Caminhos de Uso

| Objetivo | Caminho |
|----------|---------|
| Estudar a arquitetura | Ler [`docs/architecture.md`](docs/architecture.md) e [`docs/guides/lifecycle.md`](docs/guides/lifecycle.md) |
| Rodar a demo | `make install && make migrate && make seed && make run` |
| Ensaiar deploy sem tocar em Docker | copiar `.env.example`, ajustar segredos/hosts e rodar `make deploy-up` |
| Ver o que funciona hoje | [`docs/status.md`](docs/status.md) — estado factual por módulo |
| Usar como base do seu negócio | Fork, criar instância em `instances/`, configurar `Shop` no admin |
| Adotar um core app isolado | `pip install shopman-stockman` (quando publicado no PyPI) |
| Contribuir ou corrigir | Ver [`docs/ROADMAP.md`](docs/ROADMAP.md) para gaps ativos |

## Estrutura do Projeto

```
django-shopman/
├── packages/                   # 9 apps pip-instaláveis (sem dependência entre si)
│   ├── utils/                  # shopman-utils — Monetário, formatting, phone
│   ├── refs/                   # shopman-refs — Registro de refs tipadas
│   ├── offerman/               # shopman-offerman — Catálogo
│   ├── stockman/               # shopman-stockman — Estoque
│   ├── craftsman/              # shopman-craftsman — Produção
│   ├── orderman/                # shopman-orderman — Pedidos
│   ├── guestman/               # shopman-guestman — CRM
│   ├── doorman/                # shopman-doorman — Auth
│   └── payman/                 # shopman-payman — Pagamentos
│
├── shopman/                    # Namespace package (PEP 420)
│   └── shop/                   # App Django orquestrador (django-shopman)
│       ├── lifecycle.py        # dispatch() config-driven via ChannelConfig
│       ├── services/           # Lógica de negócio (stock, payment, checkout, etc.)
│       ├── adapters/           # Integrações swappable (EFI, Stripe, ManyChat, etc.)
│       ├── handlers/           # Directive handlers (stock, payment, notification, etc.)
│       ├── models/             # Shop, Channel, RuleConfig, NotificationTemplate, OmotenashiCopy
│       ├── views/              # Health/readiness endpoints
│       ├── web/                # Legacy helpers/compat; storefront/backstage são apps próprios
│       └── admin/              # Admin Unfold (shop, regras, notificações)
│
├── config/                     # Django project wrapper (settings.py, urls.py, wsgi.py)
│
├── instances/                  # Instâncias (configuração por negócio)
│   └── nelson/                 # Nelson Boulangerie (demo)
│
├── docs/                       # Documentação completa
│   ├── guides/                 # Lifecycle, auth, repo workflow, etc.
│   ├── reference/              # Data schemas, protocols, glossário
│   └── decisions/              # ADRs (Architecture Decision Records)
│
└── Makefile                    # install, test, migrate, run, seed, lint
```

## Framework (shopman/shop/)

O framework conecta os core apps para cenários de negócio concretos:

- **Lifecycle:** Coordenação config-driven. Signal `order_changed` → `dispatch(order, phase)` → services. Comportamento por canal via `ChannelConfig`.
- **Services:** Lógica de negócio. Cada service opera sobre Core services via adapters.
- **Adapters:** Integrações externas swappable via settings. `get_adapter("payment", method="pix")` → `payment_efi`.
- **Directive handlers:** Processamento assíncrono pós-commit (stock.hold, notification.send, payment.capture).

## Features

- **Storefront mobile-first** — HTMX + Alpine.js, PWA-ready
- **Checkout com PIX** — QR code, polling, auto-confirmação
- **Gestor de pedidos** — painel operador com timer, confirmação otimista, despacho KDS
- **KDS** — Kitchen Display System com múltiplas instâncias (prep, picking, expedição)
- **POS** — Ponto de venda integrado
- **Dashboard** — KPIs, charts, alertas de estoque, fechamento de caixa
- **Auth OTP** — WhatsApp-first com fallback SMS, magic links, device trust
- **Multi-canal** — balcão, delivery, WhatsApp, marketplace (iFood)
- **Notificações** — email, WhatsApp (ManyChat), console, SMS
- **Produção** — receitas, work orders, BOM, sugestão automática
- **Loyalty** — pontos, stamps, tiers (Bronze → Platinum)
- **Import/Export** — produtos e preços via CSV/Excel

## Comandos

```bash
make install          # Instala dependências + packages em modo editável
make test             # Roda todos os ~1.900 testes
make test-offerman    # Testes de um core app específico
make test-framework    # Testes do framework
make migrate          # Aplica migrações
make seed             # Popula com dados demo (Nelson Boulangerie)
make run              # Sobe servidor (localhost:8000)
make lint             # Ruff check
make deploy-check     # check --deploy + migrations check + collectstatic dry-run
make deploy-up        # build/release/web/worker via compose, sem Docker manual
make deploy-logs      # logs de web + directive worker
make deploy-down      # para containers do deploy local
```

## Convenções

- **Valores monetários:** `int` em centavos com sufixo `_q` (ex: `base_price_q = 1050` → R$ 10,50)
- **Identificadores:** `ref` (não `code`). Exceção: `Product.sku`
- **Confirmação:** Otimista — pedido auto-confirma se operador não cancela no timeout
- **Frontend:** HTMX ↔ servidor, Alpine.js ↔ DOM. Nunca `onclick`, `getElementById`, etc.
- **Comunicação entre apps:** `typing.Protocol` + adapters, sem imports diretos

## Repos

| Repo | Descrição |
|------|-----------|
| [django-shopman](https://github.com/pablondrina/django-shopman) | Monorepo (este repo) |
| [shopman-orderman](https://github.com/pablondrina/shopman-orderman) | Core: Pedidos |
| [shopman-stockman](https://github.com/pablondrina/shopman-stockman) | Core: Estoque |
| [shopman-craftsman](https://github.com/pablondrina/shopman-craftsman) | Core: Produção |
| [shopman-offerman](https://github.com/pablondrina/shopman-offerman) | Core: Catálogo |
| [shopman-guestman](https://github.com/pablondrina/shopman-guestman) | Core: CRM |
| [shopman-doorman](https://github.com/pablondrina/shopman-doorman) | Core: Auth |
| [shopman-payman](https://github.com/pablondrina/shopman-payman) | Core: Pagamentos |
| [shopman-utils](https://github.com/pablondrina/shopman-utils) | Core: Utilitários |
| [shopman-nelson](https://github.com/pablondrina/shopman-nelson) | Instância: Nelson Boulangerie |

## Documentação

- [Arquitetura](docs/architecture.md) — diagrama de camadas, Protocol/Adapter
- [Quickstart](docs/getting-started/quickstart.md) — instalação passo a passo
- [Runtime dependencies](docs/reference/runtime-dependencies.md) — contrato PostgreSQL/Redis/SQLite
- [Deploy](docs/guides/deploy.md) — imagem app, compose profiles e make deploy-*
- [Um Dia na Padaria](docs/getting-started/dia-na-padaria.md) — tutorial narrativo
- [Lifecycle](docs/guides/lifecycle.md) — guia de Lifecycles, Services, Adapters
- [Auth](docs/guides/auth.md) — autenticação OTP e device trust
- [Repo Workflow](docs/guides/repo-workflow.md) — como manter monorepo e repos sincronizados
- [Data Schemas](docs/reference/data-schemas.md) — chaves em Session.data, Order.data
- [Glossário](docs/reference/glossary.md) — termos de domínio
- [ADRs](docs/decisions/) — decisões arquiteturais

## Requisitos

| Requisito | Versão |
|-----------|--------|
| Python | ≥ 3.12 |
| Django | ≥ 5.2, < 6.0; bump coordenado para 6.0 planejado |
| Node.js | ≥ 18 (build Tailwind CSS) |
| Banco de dados | PostgreSQL 16+ em dev canônico/staging/prod; SQLite só fallback local |
| Cache/realtime | Redis 7+ em dev canônico/staging/prod; LocMem só fallback local |

## Licença

MIT — Pablo Valentini
