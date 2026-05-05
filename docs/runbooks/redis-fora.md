# Redis fora ou SSE sem fanout

## Sintoma visivel

Painel nao atualiza em tempo real, rate limit nao e compartilhado entre
processos, ou `make diagnose-runtime` aponta cache/eventstream em `WARN`/`FAIL`.

## Impacto

Operador pode trabalhar com tela stale; webhooks e pedidos podem estar corretos
no banco, mas invisiveis ate refresh manual.

## Diagnostico

```bash
make diagnose-runtime
make diagnose-health
make deploy-ps
```

Confirme `redis runtime`, `cache roundtrip` e `eventstream fanout`. Em producao,
`LocMemCache` nao e aceitavel.

## Acao imediata segura

1. Pedir refresh manual da tela operacional enquanto Redis volta.
2. Nao reiniciar banco para resolver problema de cache.
3. Subir novamente a pilha pelo wrapper:

```bash
make deploy-up
```

## Recuperacao

Quando `make diagnose-runtime` voltar a `OK`, conferir backlog e pagamentos:

```bash
make diagnose-worker
make diagnose-payments
```

## Escalar

Escalar se Redis esta acessivel mas `EVENTSTREAM_REDIS` falta, se o cache
roundtrip falha repetidamente, ou se a UI segue stale com Redis OK.

## Evidencia minima

Horario, saida de `diagnose-runtime`, status de `deploy-ps`, impacto observado
na tela e acao feita.

