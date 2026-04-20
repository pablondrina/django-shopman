# WP-GAP-08 — Quant cache reconciliation

> Entrega para fechar vetor de divergência silenciosa em `Quant._quantity`. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma
**Severidade**: 🟠 Média-alta. Guards em `Move.save/delete` são robustos, mas `Quant._quantity` pode divergir de `Σ(moves.delta)` via três vetores exploráveis (shell/migração, seed fixture, SQL direto / `.update()` queryset). Contrato "zero over-sell" depende de `_quantity` correto.

---

## Contexto

### Avaliação de risco (conduzida 2026-04-18)

Análise dedicada de `packages/stockman/` identificou que:

**Guards fortes (OK)**:
- `Move.save()` bloqueia edição de registro existente.
- `Move.delete()` bloqueia categoricamente.
- Admin de `Move` é read-only.

**Vetores de divergência reais**:

1. **`Quant.objects.create(_quantity=X)` direto** — usado em testes (`test_availability.py:34`) e potencialmente em seed/fixture. Cria Quant com `_quantity=50` e `moves.count()=0`. OK em teste isolado; perigoso se vazar para seed de produção.
2. **`Quant.objects.filter(...).update(_quantity=X)` via queryset** — usado em teste de recalculate (`test_service.py:402`). Bypass completo do Move ledger. Shell Django ou migração manual pode executar o mesmo em produção.
3. **SQL direto** — não presente no código atual, mas possível via `psql` ou migração raw.
4. **Signals futuros** — se alguém adicionar `post_save` em Move sem entender que já há `F()` update, vira double-debit.

**Defense-in-depth existente**:
- DB check `_quantity >= 0` — impede over-sell negativo, não divergência.
- Método `Quant.recalculate()` existe como utility (recompute de moves + log warning), mas é **manual** — ninguém invoca sistematicamente.
- Um teste de invariante existe em `test_service.py:398` (`test_recalculate_fixes_inconsistency`) — prova que `recalculate()` funciona, mas **não previne** divergência.

**Faltam**:
- Management command para rodar reconciliation via cron.
- Constraint no DB (ou signal/manager guard) que impede `.update(_quantity=...)`.
- Alerta operacional quando divergência é detectada.

### Veredito

Risco é **real** (vetores exploráveis existem) mas **não exposto em produção hoje** (API força `Move.save()`, testes usam `stock.receive()`). Precisa remediação **antes de crescer** — no dia que alguém rodar migração manual ou adicionar bulk op descuidado, o contrato falha silenciosamente.

---

## Escopo

### In

#### 1. Management command `recompute_quant_quantities`

- Arquivo: `packages/stockman/shopman/stockman/management/commands/recompute_quant_quantities.py`.
- Flags:
  - `--dry-run`: só reporta divergências, não corrige.
  - `--apply`: aplica `recalculate()` nos divergentes + log WARNING estruturado.
  - `--sku <sku>`: limita a um SKU específico.
- Output: tabela de (quant_pk, sku, position, current_quantity, computed_quantity, delta).
- Exit code: 0 se nenhum divergente; 1 se divergentes em dry-run; 0 se todos corrigidos em --apply.

#### 2. QuantManager guard contra `.update(_quantity=...)`

- Override `QuantManager.update()` (e queryset `.update()`) que rejeita kwargs `_quantity` unless flag `_allow_quantity_update=True` setado.
- Mensagem de erro explicativa: "Quant._quantity é cache de Σ(moves.delta). Use stock.receive/issue/adjust em vez de .update()."

#### 3. Defesa via DB constraint (triggered)

- Django constraint `CheckConstraint(_quantity >= 0)` já existe — bom.
- **Adicional**: check em `Quant.clean()` que chama `self.recalculate(commit=False)` e compara — em desenvolvimento levanta `ValidationError`. **Não** aplicado em save por performance, mas disponível para ferramentas de teste.
- (Opcional, fase 2) Trigger PostgreSQL que valida pós-Move: complexo, talvez overkill agora.

#### 4. Teste de invariante automático

- `packages/stockman/shopman/stockman/tests/test_quantity_invariant.py`:
  - Após série de operações (`receive`, `issue`, `adjust`, `hold`, `fulfill`, `release`) em múltiplos quants, validar `quant._quantity == quant.moves.aggregate(Sum('delta'))['delta__sum']` para todos os quants.
  - Teste usa Postgres (requer WP-GAP-04); skip em SQLite.

#### 5. Alerta operacional via command em cron

- Setup: `make cron` target ou doc explicando `0 3 * * * python manage.py recompute_quant_quantities --dry-run` em crontab.
- Em caso de divergência: log WARNING estruturado + (opcional) envia OperatorAlert via service existente.

#### 6. Documentação em Stockman guide

- [docs/guides/stockman.md](../guides/stockman.md) ganha seção "Integridade de `_quantity`":
  - Por que é cache (performance).
  - Por que pode divergir (vetores acima).
  - Como detectar (`recompute_quant_quantities --dry-run`).
  - Como corrigir (`--apply`).
  - Política: "nunca bypassar Move ledger".

### Out

- PostgreSQL trigger de auto-reconciliation — complexo, não se prova necessário ainda.
- Substituir `_quantity` cache por `@property` recomputada — mata performance O(1) de availability queries em escala.
- Full event sourcing — fora de escopo; Moves já são append-only ledger, basta.

---

## Entregáveis

### Novos arquivos

- `packages/stockman/shopman/stockman/management/commands/recompute_quant_quantities.py`.
- `packages/stockman/shopman/stockman/tests/test_quantity_invariant.py`.

### Edições

- [packages/stockman/shopman/stockman/models/quant.py](../../packages/stockman/shopman/stockman/models/quant.py):
  - Override `QuantManager` / `QuantQuerySet.update()` com guard.
  - Adicionar `recalculate()` check opcional em `clean()`.
  - Docstring do modelo reforçando "é cache; atualizações via Move apenas".
- [docs/guides/stockman.md](../guides/stockman.md) — nova seção.
- [Makefile](../../Makefile) (opcional): target `reconcile-stock` para rodar management command manualmente.

---

## Invariantes a respeitar

- **`Quant._quantity` permanece cache denormalizado** — não vamos mudar para @property. Performance O(1) é essencial.
- **`Move` é source of truth**: divergência detectada sempre é resolvida em favor de `Σ(moves.delta)` — recompute sobrescreve `_quantity`, nunca o contrário.
- **Guard do manager é escape-hatchable** via flag `_allow_quantity_update=True` (permissão explícita para testes/ferramentas), não fechado categoricamente — permite `recompute` fazer seu trabalho.
- **Log estruturado** em divergências detectadas: `logger.error("quant.quantity_mismatch", extra={"pk": ..., "sku": ..., "current": ..., "computed": ..., "delta": ...})`.
- **Não quebrar testes existentes** que usam `Quant.objects.create(_quantity=X)` direto — eles continuam válidos (é teste-only).
- **Documentação visível**: novo contribuidor que leia `stockman.md` entende a regra sem ter que ler código.
- **Compatibilidade com WP-GAP-04**: teste de invariante roda só em Postgres (skip em SQLite) — consistente com teste de concorrência já existente.

---

## Critérios de aceite

1. `python manage.py recompute_quant_quantities --dry-run` em Nelson seed retorna **0 divergências** — estado inicial limpo.
2. Seed incorreto (ex.: `Quant.objects.create(_quantity=999)` via shell) detectado por `--dry-run`; corrigido por `--apply`.
3. Tentativa de `Quant.objects.filter(...).update(_quantity=50)` em shell levanta erro explicativo (exceto se `_allow_quantity_update=True`).
4. `test_quantity_invariant.py` passa em Postgres após 20+ operações encadeadas (receive/issue/hold/fulfill/release alternados).
5. `docs/guides/stockman.md` tem seção "Integridade de `_quantity`" — revisada para legibilidade.
6. Management command logga WARNING estruturado em divergência (SIEM/Sentry pickáveis).
7. `make test` verde; `make test-stockman` não pula novo teste de invariante em Postgres.

---

## Referências

- Veredito de avaliação (2026-04-18): 3 vetores reais + defense-in-depth parcial + remediação P1-P4.
- [packages/stockman/shopman/stockman/models/quant.py](../../packages/stockman/shopman/stockman/models/quant.py) — `recalculate()` existente em linhas 157-186.
- [packages/stockman/shopman/stockman/models/move.py](../../packages/stockman/shopman/stockman/models/move.py) — guards existentes linhas 67-111.
- [packages/stockman/shopman/stockman/tests/test_service.py](../../packages/stockman/shopman/stockman/tests/test_service.py) — `test_recalculate_fixes_inconsistency` existente em linha 398.
- [docs/reference/system-spec.md §1.3](../reference/system-spec.md) — Stockman invariantes.
- Memória [project_stockman_scope_unified.md](.claude/memory) — contrato check↔reserve.
