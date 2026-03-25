# Documentação — Django Shopman

> Índice geral de toda a documentação do projeto.

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
| [Offering](guides/offering.md) | `shopman.offering` | Catálogo, preços, listings, bundles, coleções |
| [Stocking](guides/stocking.md) | `shopman.stocking` | Estoque, holds, moves, posições, planejamento |
| [Crafting](guides/crafting.md) | `shopman.crafting` | Receitas, work orders, BOM, coeficiente francês |
| [Ordering](guides/ordering.md) | `shopman.ordering` | Pedidos, sessões, canais, directives, fulfillment |
| [Customers](guides/customers.md) | `shopman.customers` | Clientes, contatos, grupos, loyalty, consent, RFM |
| [Auth](guides/auth.md) | `shopman.auth` | Auth OTP, device trust, bridge tokens, magic links |
| [Payments](guides/payments.md) | `shopman.payments` | Pagamentos, PIX, Stripe, intents, lifecycle |

---

## Referência Técnica

Documentação de consulta rápida gerada a partir do código.

| Documento | Conteúdo |
|-----------|----------|
| [Protocols e Adapters](reference/protocols.md) | Mapa de todos os protocols, dataclasses e adapters disponíveis |
| [Configurações](reference/settings.md) | Settings por app (STOCKING, CRAFTING, AUTH, SHOPMAN_*, etc.) com defaults |
| [Management Commands](reference/commands.md) | Comandos disponíveis com flags, exemplos e cron recomendado |
| [Exceções e Erros](reference/errors.md) | Hierarquia de exceções, códigos de erro e quando ocorrem |
| [Sinais (Signals)](reference/signals.md) | Sinais emitidos e consumidos por cada app, payload e fluxos |
| [Glossário](reference/glossary.md) | Termos de domínio: Quant, Hold, Move, Session, Order, Channel, etc. |

---

## Mapa de Apps

```
shopman-core/                        shopman-app/
├── utils        (utilitários)       ├── shop/              (identidade + regras)
├── offering     (catálogo)          ├── channels/          (orquestrador)
├── stocking     (estoque)           │   ├── handlers/      (11 handlers)
├── crafting     (produção)          │   ├── backends/      (17 backends)
├── ordering     (pedidos)           │   ├── config.py      (ChannelConfig)
├── customers    (clientes)          │   ├── presets.py     (pos, remote, marketplace)
├── auth         (autenticação)      │   ├── hooks.py       (lifecycle dispatcher)
└── payments     (pagamentos)        │   ├── setup.py       (registro centralizado)
                                     │   └── web/           (storefront)
                                     └── project/           (settings, urls)
```

---

## Mapa de Nomes (suite antiga → repo atual)

Para quem conhece a suite antiga (`django-shopman-suite`):

| Nome Antigo | Nome Atual | App Label |
|-------------|-----------|-----------|
| commons | shopman.utils | `utils` |
| offerman | shopman.offering | `offering` |
| stockman | shopman.stocking | `stocking` |
| craftsman | shopman.crafting | `crafting` |
| omniman | shopman.ordering | `ordering` |
| guestman | shopman.customers | `customers` |
| doorman | shopman.auth | `auth` |
