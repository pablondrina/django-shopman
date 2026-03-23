# Django Shopman

Sistema modular de gestao comercial para pequenos negocios (padarias, confeitarias, cafes).
Construido com Django 5.2+, arquitetura Protocol/Adapter, e foco em simplicidade operacional.

## Quickstart

```bash
# 1. Clonar e instalar
git clone <repo-url> django-shopman
cd django-shopman
make install

# 2. Criar banco e popular com dados demo (Nelson Boulangerie)
make migrate
make seed

# 3. Subir servidor
make run
# → http://localhost:8000/admin/  (admin/admin)
```

Veja [docs/getting-started/quickstart.md](docs/getting-started/quickstart.md) para detalhes.

## Estrutura do Projeto

```
django-shopman/
├── shopman-core/           # 7 apps Django independentes (pip-instalaveis)
│   ├── utils/              # Utilitarios compartilhados (monetary, formatting)
│   ├── offering/           # Catalogo: produtos, listings, precos por canal
│   ├── stocking/           # Estoque: quants, moves, holds, alertas, planejamento
│   ├── crafting/           # Producao: receitas, work orders, BOM, coef. francais
│   ├── ordering/           # Pedidos: sessoes, canais, directives, fulfillment
│   ├── attending/          # Clientes: contatos, grupos, insights RFM, enderecos
│   └── gating/             # Auth: OTP, magic links, device trust, bridge tokens
│
├── shopman-app/            # Projeto Django que orquestra tudo
│   ├── project/            # settings.py, urls.py
│   ├── shopman/            # Orquestrador: conecta core apps via handlers
│   │   ├── stock/          # Hold/commit de estoque via StockBackend
│   │   ├── payment/        # Pagamento via PaymentBackend
│   │   ├── notifications/  # Notificacoes via NotificationBackend
│   │   ├── customer/       # Resolucao de clientes via CustomerBackend
│   │   ├── pricing/        # Precos via PricingBackend
│   │   ├── confirmation/   # Confirmacao otimista de pedidos
│   │   ├── fiscal/         # Emissao fiscal via FiscalBackend
│   │   ├── accounting/     # Contabilidade via AccountingBackend
│   │   ├── returns/        # Devoluções e estornos
│   │   └── webhook/        # Webhooks de entrada (pagamento, marketplace)
│   ├── channels/           # Canais de venda (web storefront)
│   └── nelson/             # App demo: Nelson Boulangerie
│
├── docs/                   # Documentacao
│   ├── architecture.md     # Diagrama de camadas e Protocol/Adapter
│   ├── getting-started/    # Quickstart e tutorial
│   └── decisions/          # ADRs (Architecture Decision Records)
│
└── Makefile                # install, test, migrate, run, seed, lint, clean
```

## Apps Core (shopman-core)

Cada app e um pacote pip independente. Comunicacao entre apps via `typing.Protocol` — zero imports diretos.

| App | Descricao | Modelos Principais |
|-----|-----------|--------------------|
| **utils** | Monetario (`_q` centavos), formatting, phone | — |
| **offering** | Catalogo de produtos vendaveis | Product, Listing, Collection |
| **stocking** | Controle de estoque fisico | Quant, Move, Hold, Position, Batch |
| **crafting** | Producao e receitas | Recipe, WorkOrder, WorkOrderItem |
| **ordering** | Kernel de pedidos | Session, Order, Directive, Channel |
| **attending** | Gestao de clientes | Customer, ContactPoint, CustomerGroup |
| **gating** | Autenticacao e acesso | MagicCode, DeviceTrust, BridgeToken |

## Orquestrador (shopman-app)

O `shopman-app` conecta os core apps para cenarios de negocio concretos:

- **Presets de canal:** `pos()`, `remote()`, `marketplace()` — configuram comportamento por canal de venda
- **Handlers de directive:** `stock.hold`, `notification.send`, `payment.capture` — processam tarefas pos-commit
- **Protocol/Adapter:** cada integracao (estoque, pagamento, fiscal) e substituivel sem alterar o core

## Comandos Uteis

```bash
make install         # Instala dependencias + apps em modo editavel
make test            # Roda todos os ~1500 testes
make migrate         # Aplica migracoes
make seed            # Popula com dados demo (Nelson Boulangerie)
make run             # Sobe servidor de desenvolvimento
make lint            # Ruff check
make clean           # Limpa caches
```

## Convencoes

- **Valores monetarios:** `int` em centavos com sufixo `_q` (ex: `base_price_q = 1050` → R$ 10,50)
- **Identificadores:** `ref` (nao `code`). Excecao: `Product.sku`
- **Confirmacao:** Otimista — pedido e auto-confirmado se operador nao cancela no timeout
- **Comunicacao entre apps:** `typing.Protocol` + adapters, sem imports diretos

## Documentacao

- [Arquitetura](docs/architecture.md) — diagrama de camadas, Protocol/Adapter, dependencias
- [Quickstart](docs/getting-started/quickstart.md) — instalacao passo a passo
- [Um Dia na Padaria](docs/getting-started/dia-na-padaria.md) — tutorial narrativo completo
- [ADRs](docs/decisions/) — decisoes arquiteturais

## Requisitos

- Python 3.11+
- Django 5.2+
- SQLite (dev) / PostgreSQL (prod)
