# Django Shopman

![Python](https://img.shields.io/badge/python-≥3.12-blue)
![Django](https://img.shields.io/badge/django-6.0-green)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Release](https://img.shields.io/github/v/release/pablondrina/django-shopman?include_prereleases&label=release)
![Tests](https://img.shields.io/badge/tests-~5.000-brightgreen)

Django Shopman é um framework de commerce operations para pequenos negócios com operação física e remota — padarias, confeitarias, cafés, food service. Não é um e-commerce genérico; é uma base opinativa e modular para casos operacionais densos: catálogo com produção própria, estoque vivo, múltiplos canais (balcão, web, WhatsApp, marketplace), KDS, e gestão integrada.

Construído com Django 6.0, backend headless (API JSON + projections) e superfícies Nuxt 4 SSR.

## Ecossistema

O Shopman é composto por **3 camadas**:

| Camada | Onde vive | Descrição |
|--------|-----------|-----------|
| **Core Apps** | `packages/` | 11 pacotes pip independentes, cada um com domínio próprio |
| **Framework** | `shopman/` | Orquestrador (`shop`) + superfícies headless (`storefront`, `backstage`) que servem API JSON e projections |
| **Superfícies** | `surfaces/` | 6 apps Nuxt 4 SSR (loja, hub, POS, KDS, gestor, produção) + layer `operator-kit` |

> **Tenant = config + dados + marca, zero código.** Não há pacote Python de instância.
> "Nelson Boulangerie" é o `Shop` singleton + dados no DB (via `seed`) + marca + settings do deployment.

### Core Apps

Cada app é um pacote pip independente. Os cores nunca se importam entre si — a integração
é decidida pela interação (signal / adapter / directive), lei registrada na
[ADR-001](docs/decisions/adr-001-protocol-adapter.md).

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
| **Buyman** | `shopman-buyman` | `shopman.buyman` | Compras (procurement) | Material, Supplier |
| **Fiscalman** | `shopman-fiscalman` | `shopman.fiscalman` | Fiscal (NFC-e) | classificação em Product.metadata |

## Quickstart

O backend Django é **headless**: serve API JSON em `/api/v1/`. As telas vivas são os apps
Nuxt em `surfaces/`. Em dev, use **sempre `127.0.0.1`** (nunca `localhost` — o cookie de
sessão e os BFFs dependem disso).

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

# 3. Subir a API Django
make run
# → http://127.0.0.1:8000/api/v1/   (API headless)
# → http://127.0.0.1:8000/admin/    (Admin/Unfold — admin/admin em dev)

# 4. Subir as superfícies Nuxt (cada uma em seu diretório)
cd surfaces/storefront-nuxt && npm install && npm run dev   # loja      → http://127.0.0.1:3000
cd surfaces/pos-nuxt        && npm install && npm run dev   # PDV       → http://127.0.0.1:3002
# hub :3001 · kds :3003 · orders :3004 · production :3005
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
| Rodar a demo | `make install && make migrate && make seed && make run` + apps Nuxt |
| Ensaiar deploy sem tocar em Docker | copiar `.env.example`, ajustar segredos/hosts e rodar `make deploy-up` |
| Ver o que funciona hoje | [`docs/status.md`](docs/status.md) — estado factual por módulo |
| Usar como base do seu negócio | Fork, configurar `Shop`/`Channel`/`RuleConfig` no admin + seed próprio |
| Adotar um core app isolado | `pip install shopman-stockman` (quando publicado no PyPI) |
| Contribuir ou corrigir | Ver [`docs/ROADMAP.md`](docs/ROADMAP.md) para gaps ativos |

## Estrutura do Projeto

```
django-shopman/
├── packages/                   # 11 apps pip-instaláveis (sem dependência entre si)
│   ├── utils/ refs/            # shopman-utils, shopman-refs
│   ├── offerman/ stockman/     # catálogo, estoque
│   ├── craftsman/ orderman/    # produção, pedidos
│   ├── guestman/ doorman/      # CRM, auth
│   ├── payman/ buyman/         # pagamentos, compras
│   └── fiscalman/              # fiscal (NFC-e)
│
├── shopman/                    # Namespace package (PEP 420)
│   ├── shop/                   # Orquestrador: lifecycle, services, adapters, rules, handlers
│   ├── storefront/             # Superfície customer HEADLESS: api/, presentation/, intents/
│   └── backstage/              # Superfícies operador HEADLESS + Admin/Unfold
│
├── surfaces/                   # 6 apps Nuxt 4 (SSR) + 1 layer
│   ├── storefront-nuxt/        # loja do cliente (apex, :3000)
│   ├── hub-nuxt/               # Central de Apps do operador (:3001)
│   ├── pos-nuxt/               # PDV (:3002)
│   ├── kds-nuxt/               # cozinha (:3003)
│   ├── orders-nuxt/            # gestor de pedidos (:3004)
│   ├── production-nuxt/        # produção/fornadas (:3005)
│   └── operator-kit/           # Nuxt layer compartilhada dos apps de operador
│
├── config/                     # Django project wrapper + seed do deployment (Nelson)
├── docs/                       # Documentação completa (guias, ADRs, referência, planos)
└── Makefile                    # install, test, migrate, run, seed, lint, admin, deploy-*
```

## Framework (shopman/shop/)

O framework conecta os core apps para cenários de negócio concretos:

- **Lifecycle:** Coordenação config-driven. Signal `order_changed` → `dispatch(order, phase)` → services. Comportamento por canal via `ChannelConfig`.
- **Services:** Lógica de negócio. Cada service opera sobre Core services via adapters.
- **Adapters:** Integrações externas swappable via settings. `get_adapter("payment", method="pix")` → `payment_efi`.
- **Directive handlers:** Processamento assíncrono pós-commit (stock.hold, notification.send, payment.capture).

**Como os apps conversam (3 ferramentas, a interação decide):** cores nunca se importam.
*Anunciar evento sem esperar retorno* → **signal** (handler em `<core>/contrib/<alvo>/` ou no shop);
*precisar de retorno síncrono / sequenciar* → **adapter/Protocol** (settings, só com 2+ impls reais);
*comando async confiável* → **Directive**. Detalhe e exemplos no
[guia de lifecycle](docs/guides/lifecycle.md#integração-entre-apps--qual-mecanismo-usar) e na
[ADR-001](docs/decisions/adr-001-protocol-adapter.md).

## Features

- **Storefront mobile-first** — Nuxt 4 SSR no apex, PWA-ready, SEO técnico
- **Checkout com PIX** — QR code, polling + SSE, auto-confirmação
- **Gestor de pedidos** — painel operador com timer, confirmação otimista, despacho KDS
- **KDS** — Kitchen Display System com múltiplas instâncias (prep, picking, expedição)
- **POS** — Ponto de venda desktop-first com tabs, turno e caixa
- **Produção** — receitas, work orders, BOM, sugestão automática, kiosk de fornadas
- **Auth WhatsApp-first** — access link, OTP com fallback SMS, magic links, device trust
- **Multi-canal** — balcão, delivery, WhatsApp, marketplace (iFood direto, polling)
- **Delivery** — zonas, geocoding em cascata, logística externa (Machine/courier)
- **Notificações** — WhatsApp (ManyChat), email, SMS, console — swappable por adapter
- **Fiscal** — classificação NFC-e por produto (emissão via Focus NFe)
- **Compras** — fornecedores, materiais (insumos) e custos (Buyman Fase 1)
- **Loyalty** — pontos, stamps, tiers (Bronze → Platinum)
- **Tempo real por SSE** — estoque, KDS, tracking, badges ([ADR-016](docs/decisions/adr-016-sse-first-realtime.md))

## Comandos

```bash
make install          # Instala dependências + packages em modo editável
make test             # Roda todos os ~5.000 testes (cores + framework)
make test-offerman    # Testes de um core app específico
make test-framework   # Testes do framework (shop + storefront + backstage)
make admin            # Gate canônico Admin/Unfold + testes de integração
make migrate          # Aplica migrações
make seed             # Popula com dados demo (Nelson Boulangerie)
make run              # Sobe a API Django (127.0.0.1:8000)
make lint             # Ruff + Admin/Unfold
make deploy-check     # check --deploy + migrations check + collectstatic dry-run
make deploy-up        # build/release/web/worker via compose, sem Docker manual
make deploy-logs      # logs de web + directive worker
make deploy-down      # para containers do deploy local
```

## Convenções

- **Valores monetários:** `int` em centavos com sufixo `_q` (ex: `base_price_q = 1050` → R$ 10,50)
- **Identificadores:** `ref` (não `code`). Exceções: `Product.sku`, `WorkOrder.code`
- **Confirmação:** Otimista — pedido auto-confirma se operador não cancela no timeout
- **Erros de API:** dialeto canônico `{detail, field, errors}` — ver [docs/reference/errors.md](docs/reference/errors.md)
- **Integração entre apps:** signal / adapter / directive conforme a interação ([ADR-001](docs/decisions/adr-001-protocol-adapter.md))

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

## Documentação

- [Arquitetura](docs/architecture.md) — diagrama de camadas e integração entre apps
- [Quickstart](docs/getting-started/quickstart.md) — instalação passo a passo
- [Runtime dependencies](docs/reference/runtime-dependencies.md) — contrato PostgreSQL/Redis/SQLite
- [Deploy](docs/guides/deploy.md) — imagem app, compose profiles e make deploy-*
- [Um Dia na Padaria](docs/getting-started/dia-na-padaria.md) — tutorial narrativo
- [Lifecycle](docs/guides/lifecycle.md) — guia de Lifecycle, Services, Adapters, Rules
- [Doorman](docs/guides/doorman.md) — autenticação OTP, access link e device trust
- [Data Schemas](docs/reference/data-schemas.md) — chaves em Session.data, Order.data
- [Erros](docs/reference/errors.md) — dialeto canônico de erro das APIs
- [Glossário](docs/reference/glossary.md) — termos de domínio
- [ADRs](docs/decisions/) — decisões arquiteturais (ADR-001 a ADR-016)

## Requisitos

| Requisito | Versão |
|-----------|--------|
| Python | ≥ 3.12 |
| Django | ≥ 6.0, < 6.1 |
| Node.js | 22.x (apps Nuxt e buildpack DO) |
| Banco de dados | PostgreSQL 16+ em dev canônico/staging/prod; SQLite só fallback local |
| Cache/realtime | Redis 7+ em dev canônico/staging/prod; LocMem só fallback local |

## Licença

MIT — Pablo Valentini
