# ADR-005: Manter naming collisions stock/stocking e customer/attending

## Status
Accepted (2026-03-23)

## Context

O orchestrator (shopman-app) possui modulos que fazem bridge com apps do core:

| Orchestrator module | Core app         | Papel                              |
|---------------------|------------------|------------------------------------|
| `shopman.stock`     | `shopman.stocking` | Reserva e commit de estoque via diretivas |
| `shopman.customer`  | `shopman.attending` | Resolucao de clientes para pedidos   |

Os nomes `stock` e `customer` sao semanticamente proximos de `stocking` e `attending`,
o que pode causar confusao em novos desenvolvedores.

## Options Considered

### A. Renomear para nomes distintos
- `shopman.stock` -> `shopman.stock_bridge` ou `shopman.inventory_directives`
- `shopman.customer` -> `shopman.customer_bridge` ou `shopman.customer_resolver`
- **Pro:** Elimina ambiguidade
- **Con:** Churn em migracoes, imports, labels, testes. Migracao de DB (label muda).

### B. Manter os nomes atuais com documentacao
- **Pro:** Zero churn, nomes curtos, ja usados em testes e settings
- **Con:** Ambiguidade permanece, mitigada apenas por documentacao

## Decision

**Opcao B** — Manter os nomes atuais.

Razoes:
1. Os modulos do orchestrator sao THIN adapters (< 200 LOC cada). A chance de
   confusao e baixa na pratica.
2. O `label` no Django ja diferencia: `shopman_stock` vs `stocking`.
3. Renomear agora causaria churn desproporcional ao beneficio.
4. A documentacao (README.md, docs/architecture.md) ja explica a distincao.

## Consequences

- Manter a secao "Orchestrator vs Core" na documentacao de arquitetura.
- Novos modulos do orchestrator devem evitar nomes que colidam com apps do core.
- Se o projeto crescer significativamente, reconsiderar esta decisao.
