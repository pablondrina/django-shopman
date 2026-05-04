# Documentação — Django Shopman

> Índice geral de toda a documentação do projeto.

---

## Hierarquia de Documentos

| Documento | Papel |
|-----------|-------|
| [`README.md`](../README.md) | Visão geral + entrada rápida (quickstart, caminhos de uso, ecossistema) |
| [`docs/status.md`](status.md) | Estado factual — o que funciona, versões, contagem de testes real |
| [`docs/architecture.md`](architecture.md) | Verdade arquitetural — camadas, Protocol/Adapter, dependências |
| [`docs/reference/runtime-dependencies.md`](reference/runtime-dependencies.md) | Runtime canônico — PostgreSQL, Redis, fallback local e Django 6 |
| [`docs/ROADMAP.md`](ROADMAP.md) | Roadmap ativo de correções e próximos passos |
| [`docs/plans/WP-GAP-07-pre-prod-migration-playbook.md`](plans/WP-GAP-07-pre-prod-migration-playbook.md) | Playbook ativo de migração/pré-prod |
| [`docs/plans/completed/`](plans/completed/) | Arquivo de planos de execução concluídos |

---

## Início Rápido

| Documento | Descrição |
|-----------|-----------|
| [README.md](../README.md) | Visão geral do projeto, quickstart, estrutura |
| [Quickstart](getting-started/quickstart.md) | Pré-requisitos, instalação, seed, primeiro acesso |
| [Dia na Padaria](getting-started/dia-na-padaria.md) | Tutorial narrativo completo — um dia de operação |

---

## Arquitetura

| Documento | Descrição |
|-----------|-----------|
| [Arquitetura](architecture.md) | Diagrama das 7 camadas + orquestrador, Protocol/Adapter, dependências |

### Decisões Arquiteturais (ADRs)

| ADR | Título |
|-----|--------|
| [ADR-001](decisions/adr-001-protocol-adapter.md) | Protocol/Adapter — contratos entre módulos |
| [ADR-002](decisions/adr-002-centavos.md) | Centavos — valores monetários como inteiros |
| [ADR-003](decisions/adr-003-directives-sem-celery.md) | Directives sem Celery — fila assíncrona simples |
| [ADR-004](decisions/adr-004-string-refs.md) | String Refs — referências como strings |

---

## Guias de Domínio

Cada guia segue a estrutura: Conceitos → Modelos → Serviços → Protocols → Exemplos.

| Guia | App | Descrição |
|------|-----|-----------|
| [Offerman](guides/offerman.md) | `shopman.offerman` | Catálogo, preços, listings, bundles, coleções |
| [Stockman](guides/stockman.md) | `shopman.stockman` | Estoque, holds, moves, posições, planejamento |
| [Craftsman](guides/craftsman.md) | `shopman.craftsman` | Receitas, work orders, BOM, coeficiente francês |
| [Orderman](guides/orderman.md) | `shopman.orderman` | Pedidos, sessões, canais, directives, fulfillment |
| [Guestman](guides/guestman.md) | `shopman.guestman` | Clientes, contatos, grupos, loyalty, consent, RFM |
| [Doorman](guides/doorman.md) | `shopman.doorman` | Auth OTP, device trust, bridge tokens, magic links |
| [Payments](guides/payments.md) | `shopman.payman` | Pagamentos, PIX, Stripe, intents, lifecycle |
| [Lifecycle](guides/lifecycle.md) | `shopman/shop` | Orquestrador: Lifecycle, Services, Adapters, Rules |
| [Fechamento do dia](guides/day-closing.md) | `shopman` | Sobras, não vendidos, D-1 em `ontem`, às cegas vs vendas |

---

## Referência Técnica

Documentação de consulta rápida gerada a partir do código.

| Documento | Conteúdo |
|-----------|----------|
| [Protocols e Adapters](reference/protocols.md) | Mapa de todos os protocols, dataclasses e adapters disponíveis |
| [Runtime dependencies](reference/runtime-dependencies.md) | Contrato PostgreSQL/Redis/SQLite, SSE, deploy e Django 6 |
| [Configurações](reference/settings.md) | Settings por app (STOCKMAN, CRAFTSMAN, DOORMAN, SHOPMAN_*, etc.) com defaults |
| [Management Commands](reference/commands.md) | Comandos disponíveis com flags, exemplos e cron recomendado |
| [Exceções e Erros](reference/errors.md) | Hierarquia de exceções, códigos de erro e quando ocorrem |
| [Sinais (Signals)](reference/signals.md) | Sinais emitidos e consumidos por cada app, payload e fluxos |
| [Glossário](reference/glossary.md) | Termos de domínio: Quant, Hold, Move, Session, Order, Channel, etc. |
| [Data Schemas](reference/data-schemas.md) | Inventário de chaves em Session.data, Order.data, Directive.payload |
| [Filtro de Design de Superfícies](reference/design-surface-filter.md) | Checklist transversal para UI: tipografia, ícones, espaçamento, contraste, foco, responsividade e estados |

---

## Mapa de Apps

```
packages/                            framework/
├── utils        (utilitários)       ├── shop/              (orquestrador)
├── refs         (refs tipadas)      │   ├── handlers/      (directive handlers)
├── offerman     (catálogo)          │   ├── adapters/      (integrações swappable)
├── stockman     (estoque)           │   ├── config.py      (ChannelConfig)
├── craftsman    (produção)          │   ├── services/      (orquestração)
├── orderman      (pedidos)           │   ├── lifecycle.py   (dispatcher config-driven)
├── guestman     (clientes)          │   ├── rules/         (RuleConfig engine)
├── doorman      (autenticação)      │   └── views/         (health/readiness)
└── payman       (pagamentos)        ├── storefront/        (customer web/API)
                                     ├── backstage/         (operador /gestor)
                                     └── config/            (settings, urls)
```

---

## Roadmap e Planos

| Documento | Descrição |
|-----------|-----------|
| [ROADMAP.md](ROADMAP.md) | Próximos passos (P1-P6) e nice-to-haves |
| [plans/completed/](plans/completed/) | Planos de execução concluídos (Refactor, Consolidation, Hardening, Bridge) |

---

## Mapa de Nomes (suite antiga → repo atual)

Para quem conhece a suite antiga (`django-shopman-suite`):

| Nome Antigo | Nome Atual | App Label |
|-------------|-----------|-----------|
| commons | shopman.utils | `utils` |
| offerman | shopman.offerman | `offerman` |
| stockman | shopman.stockman | `stockman` |
| craftsman | shopman.craftsman | `craftsman` |
| orderman | shopman.orderman | `orderman` |
| guestman | shopman.guestman | `guestman` |
| doorman | shopman.doorman | `doorman` |
