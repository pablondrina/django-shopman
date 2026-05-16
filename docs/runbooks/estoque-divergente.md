# Estoque divergente

## Sintoma visivel

Operador ve saldo fisico diferente do sistema, fechamento mostra erro de
reconciliacao ou produto vendavel fica negativo/indisponivel sem motivo.

## Impacto

Venda de item indisponivel, ruptura falsa, perda nao registrada ou fechamento
incorreto.

## Diagnostico

```bash
make diagnose-worker
make diagnose-health
```

No admin, verificar alertas `stock_discrepancy`, `stock_low` e a tela de
fechamento do dia. O fechamento registra `reconciliation_errors` quando vendido
e disponivel nao batem.

## Acao imediata segura

1. Pausar venda do SKU afetado se houver risco de promessa falsa ao cliente.
2. Registrar contagem fisica e usuario responsavel.
3. Nao apagar movimentos; estoque e auditavel por movimentos.

## Recuperacao

- Se a divergencia veio de directive parada, recuperar worker primeiro.
- Se veio de contagem fisica, lançar ajuste pelo fluxo operacional existente.
- Se veio de producao, revisar OP, lote e yield antes de corrigir saldo.

## Escalar

Escalar se o SKU e de alto giro, se ha lote/rastreabilidade envolvida, se a
divergencia afeta pedidos pagos ou se o fechamento ja foi realizado.

## Evidencia minima

SKU, saldo sistema, contagem fisica, lote/posicao, pedidos afetados, usuario e
saida de diagnostico.

