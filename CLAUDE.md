# CLAUDE.md — Django Shopman

Instruções para agentes de código que trabalham neste repositório.

## Estrutura do Projeto

```
shopman-core/           8 apps pip-instaláveis (sem dependência entre si)
├── utils/              Utilitários compartilhados (monetary, phone, admin)
├── offering/           Catálogo: produtos, preços, listings, coleções
├── stocking/           Estoque: quants, moves, holds, posições
├── crafting/           Produção: receitas, work orders, BOM
├── ordering/           Pedidos: sessions, orders, channels, directives
├── customers/          Clientes: customers, contatos, grupos, endereços
├── auth/               Auth: OTP, device trust, bridge tokens
└── payments/           Pagamentos: intents, transactions, service

shopman-app/            Orquestrador + canais
├── shop/               Loja (singleton), promoções, cupons, seed
├── channels/           Orquestrador (conecta core apps via handlers/backends)
│   ├── handlers/       11 handlers (stock, payment, notification, etc.)
│   ├── backends/       17 backends (stock, payment_*, notification_*, etc.)
│   ├── config.py       ChannelConfig dataclass
│   ├── presets.py      pos(), remote(), marketplace()
│   ├── topics.py       Constantes de tópicos de directives
│   ├── hooks.py        Lifecycle hooks (order_changed → pipeline)
│   ├── setup.py        Registro centralizado de handlers e backends
│   ├── protocols.py    Re-exporta protocols + define Stock/Customer/Notification
│   ├── webhooks.py     Webhook Efi PIX
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

## Como Rodar

```bash
make test              # Todos os ~1.878 testes (8 suites)
make test-offering     # Apenas offering
make test-stocking     # Apenas stocking
make test-shopman-app  # Orquestrador + nelson + integration
make lint              # Ruff
make run               # Dev server (localhost:8000)
make seed              # Popular banco com dados Nelson Boulangerie
make migrate           # Migrações
```

## O Que NÃO Fazer

- **Não inventar features** durante migração ou refatoração.
- **Não usar jargão inventado** — nomes devem ser descritivos e auto-explicativos.
- **Não deixar resíduos** em renames (migrações serão resetadas no projeto novo).
- **Não assumir problemas** sem consultar ADRs e estado atual do projeto.

## Referências

- [REFACTOR-PLAN.md](REFACTOR-PLAN.md) — Plano original de refatoração (WP-0 a WP-R5, todos completos)
- [CONSOLIDATION-PLAN.md](CONSOLIDATION-PLAN.md) — Plano de consolidação pós-refatoração
- [docs/](docs/README.md) — Documentação completa (guias, ADRs, referência técnica)
- [docs/reference/glossary.md](docs/reference/glossary.md) — Glossário de termos de domínio
