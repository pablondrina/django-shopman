# ADR-005: Resolver naming collisions stock/stocking e customer/attending

## Status
Superseded (2026-03-23)

Decisao original (Opcao B — manter nomes) foi revertida em favor de rename.

## Context

O orchestrator (shopman-app) possuia modulos com nomes semanticamente proximos das apps core:

| Orchestrator (antigo) | Orchestrator (novo) | Core app | Papel |
|---|---|---|---|
| `shopman.stock` | `shopman.inventory` | `shopman.stocking` | Reserva e commit de estoque via diretivas |
| `shopman.customer` | `shopman.identification` | `shopman.attending` | Resolucao de clientes para pedidos |

## Decision

**Opcao A** — Renomear para nomes distintos.

- `shopman.stock` → `shopman.inventory`
- `shopman.customer` → `shopman.identification`

Razoes:
1. Projeto novo, sem legado. Nao ha motivo para manter ambiguidade.
2. Todos os demais modulos do orchestrator (confirmation, pricing, payment, fiscal,
   accounting, notifications, returns, webhook) ja possuem nomes distintos das apps core.
3. Os modulos nao possuem migrations — rename tem zero impacto em DB.
4. Consistencia com o padrao adotado no restante da refatoracao.

## Consequences

- Nomes do orchestrator agora sao inequivocos.
- Novos modulos do orchestrator devem seguir o mesmo padrao: nomes que descrevem
  a concern sem colidir com apps core.
