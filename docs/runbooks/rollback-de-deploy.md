# Rollback de deploy quebrado

## Sintoma visivel

Apos um deploy: health/readiness falha, erro 500 em massa, regressao funcional
grave (checkout, pagamento, KDS) ou migration que travou/quebrou o schema.

## Impacto

Operacao em producao degradada ou fora do ar. Cada minuto conta — mas reverter
sem entender o tipo de mudanca pode piorar (especialmente migration).

## Diagnostico

```bash
make diagnose-health
make diagnose-runtime
make deploy-logs        # self-hosted; na DigitalOcean, ver logs do app/release job
```

Antes de reverter, classifique a mudanca do deploy (decisivo para a estrategia):

- **So codigo** (sem migration nova).
- **Migration aditiva** (expand — coluna/chave nova, nada removido).
- **Migration destrutiva** (contract — removeu campo/coluna/constraint).
- **Data migration** (backfill).

Ver os tipos e a tabela de rollback em
[`production-upgrades.md`](../guides/production-upgrades.md#rollback-por-tipo-de-mudança).

## Acao imediata segura

1. Congelar novos deploys.
2. Preservar horario do deploy, commit/deployment id e a primeira tela afetada.
3. Se houver suspeita de corrupcao de dado, **tirar/registrar o snapshot do banco
   agora** (antes de qualquer ajuste).

## Recuperacao — rollback de codigo

Migration **aditiva** ou **so codigo**: o rollback e seguro por redeploy da
release anterior. Coluna/chave nova fica orfa e inofensiva (e por isso que o
expand-contract do ADR-015 mantem todo deploy reversivel, menos o contract).

**DigitalOcean App Platform** (staging/prod):

1. Identificar o ultimo deployment verde:
   ```bash
   doctl apps list-deployments <APP_ID>
   ```
2. Reverter para ele pelo painel (Deployments → Rollback) ou disparar um novo
   deployment fixado no ultimo commit verde. Confirmar que o release job
   **nao** roda migration destrutiva nova.
3. Validar: `/health/`, `/ready/`, `/menu/`, login do operador, um pedido ponta
   a ponta.

**Self-hosted (compose):**

1. `git checkout <commit-verde>`
2. `make deploy-up` (build + release + web/worker).
3. Validar health/readiness e um fluxo real.

## Recuperacao — migration destrutiva (contract)

**Nao ha rollback barato.** O deploy de contract so deve ter rodado quando o
codigo anterior ja nao dependia do que foi removido (regra do ADR-015). Se mesmo
assim quebrou:

1. Restaurar o banco do snapshot pre-deploy.
2. Redeploy do codigo anterior.
3. Reconciliar pagamento em dry-run antes de qualquer ajuste manual:
   ```bash
   make reconcile-financial-day dry_run=1
   ```

Data migration (backfill) e idempotente por desenho — reexecucao e segura; se
corrompeu dado, restore do snapshot.

## Pos-rollback

- Confirmar `make diagnose-worker` sem backlog stuck e `make diagnose-payments`
  sem divergencia.
- Se houve queda durante pagamento, reconciliar o dia antes de reabrir.
- Abrir post-mortem curto: o que o deploy mudou, por que o gate
  (`make test-migrations`, `release-readiness-strict`, staging) nao pegou.

## Escalar

Escalar imediatamente: migration destrutiva quebrada, divergencia financeira
apos rollback, ou indisponibilidade acima de poucos minutos sem causa clara.

## Evidencia minima

Horario do deploy e do rollback, commit/deployment id (quebrado e revertido),
tipo da mudanca, saida de health/runtime, snapshot tirado (se houve) e o
primeiro fluxo validado apos recuperacao.
