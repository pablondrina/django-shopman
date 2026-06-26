# ADR-015 - Política de backward-compat e migrations pós-produção

**Status:** Accepted; ativa a partir do go-live (`git tag go-live-v1`)
**Data:** 2026-06-26
**Escopo:** migrations, renames, política de código pós-produção, WP-GAP-07

> O [WP-GAP-07](../plans/WP-GAP-07-pre-prod-migration-playbook.md) previa um
> `adr-011`; o número 011 já é `formula-and-cashshift`. Esta é a ADR equivalente,
> com o próximo número livre (015).

---

## Contexto

O projeto operou toda a fase de dev solo sob duas regras do `CLAUDE.md`:

- *"Zero residuals em renames — migrações serão resetadas."*
- *"Zero backward-compat aliases — projeto novo, sem consumidor externo legado."*

Ambas são corretas **enquanto não existe banco de produção com dado real**:
refactor é barato, migrations são descartáveis, não há cliente para quebrar.

No segundo em que existir um banco de produção da Nelson com pedidos, clientes,
ordens de produção e ledger de pagamento reais, essas duas regras passam a ser
**perigosas**: um `reset` apaga histórico, e remover um nome num único deploy
quebra qualquer leitura em voo (request, worker, sessão serializada).

Esta ADR formaliza a virada de política descrita no WP-GAP-07.

## Decisão

A virada **só vale a partir do go-live** (quando `git tag go-live-v1` for
aplicado). Antes disso, as regras atuais do `CLAUDE.md` seguem valendo.

### 1. Migrations são append-only pós go-live

- A última migration `reset`/`squash` é **evento único**, executada no go-live
  (WP-GAP-07). Depois dela, **nunca mais** `reset`.
- Toda mudança de modelo vira migration incremental versionada.
- **Nunca editar uma migration já aplicada em produção.** Correção é uma
  migration nova.

### 2. Backward-compat aliases permitidos em janela explícita

A partir do go-live, aliases/compat temporários são **permitidos** durante uma
janela de transição explícita (referência: 1 sprint), com:

- marcador no código `# DEPRECATED(remove in v{version})` e
- TODO rastreável com prazo de remoção.

Isso habilita o padrão **expand-contract** para renames sem downtime (adicionar
o novo → backfill → migrar leituras/escritas → remover o antigo no deploy
seguinte). Detalhe operacional em
[`docs/guides/production-upgrades.md`](../guides/production-upgrades.md).

### 3. Renome de chave em `Session.data` / `Order.data`

JSONFields seguem o mesmo padrão expand-contract: data migration de backfill +
lookup condicional (lê chave nova, cai para a antiga) durante a janela, até a
remoção. Respeitar o contrato `CommitService._do_commit` (Core é sagrado).

### 4. O gate `make test-migrations`

[`scripts/check_migrations.py`](../../scripts/check_migrations.py) prova schema
limpo do zero + grafo consistente em todo deploy. A partir do go-live ganha o
replay de baseline (`SHOPMAN_MIGRATIONS_BASELINE`) — validar que o dado real
sobrevive ao upgrade.

## Consequências

- Refactor pós-prod fica mais caro e mais disciplinado — é o preço de ter dado
  real. O custo é intencional.
- Agentes futuros precisam saber que "zero backward-compat" foi **superado** no
  go-live; por isso o `CLAUDE.md` aponta para esta ADR.
- A janela de transição precisa de disciplina de remoção: alias sem prazo vira
  dívida permanente. O marcador `# DEPRECATED(remove in v{version})` é
  obrigatório, não decorativo.

## Referências

- [WP-GAP-07 pre-prod migration playbook](../plans/WP-GAP-07-pre-prod-migration-playbook.md)
- [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md)
- [production-upgrades.md](../guides/production-upgrades.md)
