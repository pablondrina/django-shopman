# PostgreSQL lento ou indisponivel

## Sintoma visivel

Health/readiness falha, paginas demoram, pedidos nao salvam, worker nao consome
diretivas ou transacoes ficam penduradas.

## Impacto

Operacao inteira fica em risco: pedido, pagamento, estoque e fechamento dependem
do banco.

## Diagnostico

```bash
make diagnose-runtime
make diagnose-health
make deploy-ps
make deploy-logs
```

`database roundtrip` deve estar `OK`. Em operacao real, SQLite e apenas fallback
local, nao runtime canonico.

## Acao imediata segura

1. Parar tentativas manuais repetidas de criar/cancelar pedido.
2. Preservar horario de inicio e telas afetadas.
3. Se o banco voltou, rode:

```bash
make diagnose-worker
make diagnose-payments
```

## Recuperacao

Confirmar migrations aplicadas, readiness OK e backlog sem stuck. Se houve
queda durante pagamento, reconciliar em dry-run antes de qualquer ajuste manual.

## Escalar

Escalar qualquer indisponibilidade acima de poucos minutos, erro de migration,
deadlock recorrente ou divergencia financeira apos retorno.

## Evidencia minima

Inicio/fim, saida de runtime/health, logs de erro, pedidos afetados e a primeira
acao executada apos recuperacao.

