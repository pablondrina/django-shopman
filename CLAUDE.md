# CLAUDE.md — Django Shopman

Instruções para agentes de código que trabalham neste repositório.

## Estrutura do Projeto

```
shopman-core/           7 apps pip-instaláveis (sem dependência entre si)
├── utils/              Utilitários compartilhados (monetary, phone, admin)
├── offering/           Catálogo: produtos, preços, listings, coleções
├── stocking/           Estoque: quants, moves, holds, posições
├── crafting/           Produção: receitas, work orders, BOM
├── ordering/           Pedidos: sessions, orders, channels, directives
├── attending/          Clientes: customers, contatos, grupos, endereços
└── gating/             Auth: OTP, device trust, bridge tokens

shopman-app/            Orquestrador + canais + demo
├── shopman/            Orquestrador (conecta core apps via backends)
│   ├── inventory/      Estoque → pedido
│   ├── identification/ Cliente → pedido
│   ├── confirmation/   Confirmação otimista
│   ├── notifications/  Notificações
│   ├── payment/        Pagamento (PIX)
│   ├── pricing/        Precificação
│   ├── accounting/     Contabilidade
│   ├── fiscal/         Fiscal
│   ├── returns/        Devoluções
│   └── webhook/        Webhooks externos
├── channels/web/       Storefront (Django templates + HTMX)
└── nelson/             App demo "Nelson Boulangerie"
```

## Convenções Ativas

- **`ref` not `code`**: Identificadores textuais são `ref`. Exceção única: `Product.sku`.
- **Centavos com `_q`**: Valores monetários são inteiros em centavos, sufixo `_q`. Ex: `price_q = 1500` → R$ 15,00.
- **Confirmação otimista**: Pedido auto-confirma se operador não cancela dentro do prazo.
- **Zero residuals em renames**: Ao renomear, zerar TUDO (variáveis, strings, comments, docstrings). Nada de `# formerly X`.
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
