# Production upgrades — zero-downtime, renames e rollback

> Playbook operacional para mudar schema e dados **com a Nelson em produção e
> dado real**. Vale **a partir do go-live** (ver
> [ADR-015](../decisions/adr-015-backward-compat-policy-post-prod.md)). Antes do
> go-live as regras de dev solo (`reset` livre, zero alias) ainda valem.

Pré-requisito de todo deploy pós-prod: `make test-migrations` verde (schema
limpo do zero + grafo consistente — [`scripts/check_migrations.py`](../../scripts/check_migrations.py)).

---

## Princípios

1. **Migrations são append-only.** Nunca `reset`, nunca editar migration
   aplicada. Correção é migration nova.
2. **Toda mudança é reversível ou expand-contract.** Um deploy nunca pode
   quebrar a versão de código ainda em voo (requests, workers, sessões
   serializadas).
3. **Backup antes de migrar.** Toda migration de prod roda depois de snapshot do
   banco e depois de validada em staging com dado representativo.

---

## Padrão expand-contract (renomear/remover sem downtime)

Nunca renomeie/remova num único deploy. Quebre em fases, cada uma é um deploy:

1. **Expand** — adicione o novo (campo/coluna/chave). Migration aditiva, sem
   remover nada. Código novo escreve nos dois; lê o novo com fallback no antigo.
2. **Backfill** — data migration que copia antigo → novo para as linhas
   existentes. Idempotente e em lotes se a tabela for grande.
3. **Migrate reads/writes** — todo o código passa a usar só o novo. O antigo
   fica órfão mas presente.
4. **Contract** — no deploy **seguinte**, remova o antigo (campo + código).
   Janela de transição de referência: 1 sprint, com `# DEPRECATED(remove in
   v{version})` marcando o que sai.

### Exemplo A — renomear um campo de model

Renomear `Order.note` → `Order.observation`:

```
Deploy 1 (expand):   add observation (nullable); save escreve nos dois.
Deploy 1 (backfill): data migration observation = note onde observation IS NULL.
Deploy 2 (migrate):  leitura/escrita só em observation.
Deploy 3 (contract): remove note (migration + código).
```

Nunca `RenameField` direto em tabela grande sob tráfego — ele reescreve sob lock.

### Exemplo B — adicionar índice em tabela grande

Use `AddIndexConcurrently` (Postgres) dentro de uma migration com
`atomic = False`. Índice concorrente não pega lock de escrita longo. Valide a
duração em staging com volume representativo antes de prod.

### Exemplo C — mudar constraint / NOT NULL

1. Adicione a coluna nullable (expand).
2. Backfill o default.
3. Adicione a constraint `NOT NULL`/`CHECK` num deploy seguinte, depois que todo
   o código já garante o invariante. Em Postgres, valide a constraint em dois
   passos (`NOT VALID` → `VALIDATE CONSTRAINT`) para evitar lock de tabela.

---

## Renomear chave em `Session.data` / `Order.data`

Estes JSONFields são o padrão de extensibilidade do Core (ver
[data-schemas.md](../reference/data-schemas.md)). **Core é sagrado** — siga o
contrato existente, não invente fluxo paralelo.

O contrato Session→Order é a lista explícita em
[`CommitService._do_commit`](../../packages/orderman/shopman/orderman/services/commit.py)
(hoje: `customer`, `fulfillment_type`, `delivery_address`, `delivery_date`,
`payment`, `delivery_fee_q`, `is_gift`, …). Renomear uma chave aqui é
expand-contract de dados:

1. **Expand** — serializers/handlers passam a **ler** a chave nova com fallback
   na antiga: `data.get("nova", data.get("antiga"))`. Escrevem a nova.
2. **Backfill** — data migration percorre `Session`/`Order` existentes copiando
   `antiga → nova` em `data`.
3. **Contract** — depois da janela, remova o fallback e a chave antiga da lista
   de `_do_commit` e dos serializers.

Sessões serializadas/em voo durante o deploy 1 ainda carregam a chave antiga —
por isso o fallback de leitura é obrigatório na fase expand.

---

## Checklist pré-deploy (produção)

- [ ] `make test` verde no commit de release.
- [ ] `make test-migrations` verde (inclui `SHOPMAN_MIGRATIONS_BASELINE` no go-live).
- [ ] `Runtime Gate` verde (PostgreSQL + Redis).
- [ ] `make release-readiness-strict` verde.
- [ ] `python manage.py check --deploy` verde com secrets/hosts reais.
- [ ] **Backup do banco de produção** tirado e localização registrada.
- [ ] Migration testada em **staging com dado representativo** (duração medida).
- [ ] Plano de rollback escrito para **esta** mudança (ver abaixo).
- [ ] Janela de deploy e responsável definidos.

---

## Rollback por tipo de mudança

| Mudança | Rollback |
|---|---|
| Só código (sem migration) | Redeploy da release anterior. |
| Migration **aditiva** (expand) | Redeploy do código anterior; a coluna/chave nova fica órfã e inofensiva. **Não** reverter a migration sob tráfego. |
| Migration **destrutiva** (contract) | **Não há rollback barato** — por isso contract só roda quando o código anterior já não depende do removido. Recuperação = restore do backup. |
| Data migration (backfill) | Idempotente por desenho; reexecução segura. Se corrompeu, restore do backup. |

Regra de ouro: **só faça contract (remoção) quando o rollback de código não
precisar do que você removeu.** Isso mantém todo deploy reversível por redeploy,
exceto o contract — que é planejado, não emergencial.

Procedimento operacional de reverter um deploy quebrado (DigitalOcean App
Platform, worker, migrations) está em
[`docs/runbooks/`](../runbooks/README.md) (runbook de rollback).

---

## Feature flags para rollout gradual

Comportamento novo arriscado entra atrás de flag (settings/env ou
`RuleConfig`), default desligado. Liga em staging → fração → 100%. Desliga sem
deploy se der ruim. Use o padrão já existente de `RuleConfig`/`Shop.defaults`
para flags config-driven em vez de `if settings.DEBUG`.

---

## Referências

- [ADR-015 — backward-compat pós-prod](../decisions/adr-015-backward-compat-policy-post-prod.md)
- [WP-GAP-07 playbook](../plans/WP-GAP-07-pre-prod-migration-playbook.md)
- [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md)
- [data-schemas.md](../reference/data-schemas.md) — chaves de `Session.data`/`Order.data`
- [`scripts/check_migrations.py`](../../scripts/check_migrations.py) — `make test-migrations`
