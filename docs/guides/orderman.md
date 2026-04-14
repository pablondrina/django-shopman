# Orderman — Pedidos e Sessões

## Visão Geral

O app `shopman.orderman` gerencia o ciclo completo de pedidos: sessões de compra, commit atômico, directives pós-commit, máquina de estados e fulfillment. A arquitetura é baseada em canais, com registry de validators, modifiers e directive handlers.

## Conceitos

### Canal (`Channel`)
Origem do pedido (balcão, WhatsApp, iFood). Define políticas de preço, edição, fluxo de confirmação e directives pós-commit.

### Sessão (`Session`)
Carrinho de compras temporário num canal. Estado: `open → committed` ou `abandoned`.

### Commit
Transformação atômica de Session em Order. Pipeline: validações → criação do pedido → snapshot → enfileiramento de directives.

### Directive
Comando assíncrono pós-commit (ex: `stock.hold`, `notification.send`). Processado por handlers registrados via topic.

### Idempotência
Cada commit tem uma `idempotency_key` que previne duplicação. Requests duplicados retornam o resultado cacheado.

## Serviços (entrada pública)

```python
from shopman.orderman.services.modify import ModifyService
from shopman.orderman.services.commit import CommitService
from shopman.orderman.services.resolve import ResolveService
from shopman.orderman.services.write import SessionWriteService
```

## Nota sobre compatibilidade de nomes

Este guia substitui o antigo `guides/ordering.md` (nomenclatura anterior do pacote; arquivo removido).

