# CLAUDE.md — Django Shopman

Instruções para agentes de código que trabalham neste repositório.

## Estrutura do Projeto

```
shopman-core/           8 apps pip-instaláveis (sem dependência entre si)
├── utils/              Utilitários compartilhados (monetary, phone, admin)
├── offering/           Catálogo: produtos, preços, listings, coleções, bundles
├── stocking/           Estoque: quants, moves, holds, posições, alertas, planejamento
├── crafting/           Produção: receitas, work orders, BOM, sugestão
├── ordering/           Pedidos: sessions, orders, channels, directives, fulfillment
├── customers/          Clientes: customers, contatos, grupos, loyalty, RFM
├── auth/               Auth: OTP, device trust, bridge tokens, magic links
└── payments/           Pagamentos: intents, transactions, service

shopman-app/            Orquestrador + canais
├── shop/               Loja (singleton), promoções, cupons, modifiers, validators
│   ├── models.py       Shop, Promotion, Coupon
│   ├── modifiers.py    D1, Promotion, Coupon, Employee, HappyHour modifiers
│   ├── validators.py   BusinessHours, MinimumOrder validators
│   ├── dashboard.py    Dashboard admin (KPIs, charts, tables, D-1 stock)
│   └── admin.py        Admin para Shop, Promotion, Coupon
├── channels/           Orquestrador (conecta core apps via handlers/backends)
│   ├── config.py       ChannelConfig dataclass (7 aspectos)
│   ├── presets.py      pos(), remote(), marketplace()
│   ├── topics.py       Constantes canônicas de tópicos de directives
│   ├── hooks.py        Lifecycle dispatcher (order_changed → pipeline → directives)
│   ├── setup.py        Registro centralizado de handlers, backends, signals
│   ├── protocols.py    Contratos: Stock, Customer, Notification, Pricing backends
│   ├── confirmation.py Helpers de confirmação + cascata
│   ├── notifications.py Registry + dispatch de notificações
│   ├── webhooks.py     Webhook Efi PIX
│   ├── handlers/       17 handlers + 6 modifiers (stock, payment, notification, loyalty, fulfillment, etc.)
│   ├── backends/       16 backends (stock, payment_*, notification_*, pricing, etc.)
│   ├── api/            API REST (DRF)
│   └── web/            Storefront (Django templates + HTMX)
└── project/            settings.py, urls.py, wsgi
```

## Convenções Ativas

- **`ref` not `code`**: Identificadores textuais são `ref`. Exceção única: `Product.sku`.
- **Centavos com `_q`**: Valores monetários são inteiros em centavos, sufixo `_q`. Ex: `price_q = 1500` → R$ 15,00.
- **Confirmação otimista**: Pedido auto-confirma se operador não cancela dentro do prazo.
- **Zero residuals em renames**: Ao renomear, zerar TUDO (variáveis, strings, comments, docstrings). Nada de `# formerly X`.
- **Zero backward-compat aliases**: Projeto novo, do zero. Não há consumidores externos. Nunca criar aliases tipo `OldName = NewName`. Apagar o nome antigo completamente.
- **Offering = somente produtos vendáveis**: Insumos ficam em Stocking/Crafting, nunca no Offering.
- **Frontend: HTMX ↔ servidor, Alpine.js ↔ DOM**:
  - **HTMX**: toda comunicação com servidor (GET, POST, polling, swaps). Incluindo `hx-on::before-request`/`after-request` para estados visuais de loading atrelados a requests.
  - **Alpine.js**: todo estado local na tela (abrir/fechar, toggles, dropdowns, modals, steppers, validação client-side, contadores, masks).
  - **NUNCA**: `onclick="..."`, `onchange="..."`, `document.getElementById`, `classList.toggle/add/remove` em templates. Usar `@click`, `x-show`, `x-data`, `x-text`, `$store`.
  - **Exceção**: IntersectionObserver e APIs do browser que não têm equivalente Alpine (geolocation, clipboard, service worker).

## Como Rodar

```bash
make test              # Todos os ~2.444 testes (1.532 core + 912 app)
make test-offering     # Apenas offering
make test-stocking     # Apenas stocking
make test-shopman-app  # Orquestrador + nelson + integration
make lint              # Ruff
make run               # Dev server (localhost:8000)
make seed              # Popular banco com dados Nelson Boulangerie
make migrate           # Migrações
```

## Core é Sagrado — Regras de Integridade

O `shopman-core/` é um conjunto de 8 apps pip-instaláveis, muito bem desenhado, robusto e flexível.
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

- **Não alterar o Core sem entender como ele já funciona** — leia services, handlers, e testes primeiro.
- **Não inventar features** durante migração ou refatoração.
- **Não usar jargão inventado** — nomes devem ser descritivos e auto-explicativos.
- **Não deixar resíduos** em renames (migrações serão resetadas no projeto novo).
- **Não assumir problemas** sem consultar ADRs e estado atual do projeto.

## Referências

- [docs/reference/data-schemas.md](docs/reference/data-schemas.md) — **Obrigatório**: inventário de chaves em Session.data, Order.data, Directive.payload
- [PRODUCTION-PLAN.md](PRODUCTION-PLAN.md) — Plano de produção: WP-F0 a WP-F18 (UX, operação, canais, governance)
- [EVOLUTION-PLAN.md](EVOLUTION-PLAN.md) — Plano completo: WP-E1 a WP-E6 (disponibilidade, loyalty, cartão, dashboard, notificações, API)
- [docs/ROADMAP.md](docs/ROADMAP.md) — Visão geral de próximos passos e ideias futuras
- [docs/](docs/README.md) — Documentação completa (guias, ADRs, referência técnica)
- [docs/guides/channels.md](docs/guides/channels.md) — Guia do orquestrador (ChannelConfig, presets, handlers)
- [docs/reference/glossary.md](docs/reference/glossary.md) — Glossário de termos de domínio

### Planos Completos (arquivo)

Todos os planos de execução foram concluídos e arquivados em `docs/plans/completed/`:
- REFACTOR-PLAN (WP-0 a WP-R5), CONSOLIDATION-PLAN (C1-C6),
  HARDENING-PLAN (H0-H5), BRIDGE-PLAN (B1-B7), RESTRUCTURE-PLAN, WORKPACKAGES
