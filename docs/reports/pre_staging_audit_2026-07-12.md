# Auditoria pré-staging — liberar para testes humanos — 2026-07-12

Auditoria de dívida técnica que bloqueie ou comprometa a liberação do staging para a primeira
leva de testadores humanos. Cada item foi verificado contra o código real e o estado do `main`
(`cb633fe4`). Metodologia: `make test`/`make lint` completos, `makemigrations --check`, `check
--deploy`, `make seed`, grep de marcadores, leitura de `config/settings.py` + specs `.do/`, diff
de worktrees, e reconciliação dos relatórios de QA/pré-alpha contra o histórico do `main`.

## Veredito

**Pode liberar o staging.** Nenhum blocker. O `main` está internamente consistente: migrações
limpas, suíte verde (exceto 2 testes caplog pré-existentes que falham só localmente), todos os
achados P0/P1 do QA exploratório e da análise pré-alpha corrigidos e mergeados, seed roda limpo
com o fix do P0. Os pontos de ⚠️ abaixo são higiene/qualidade — resolver sim, mas não travam a
primeira leva de testadores.

| # | Item | Status |
|---|------|--------|
| 1 | Testes + lint | ⚠️ Atenção (suíte verde; `make test` local aborta pelos 2 caplog) |
| 2 | Migrações pendentes | ✅ OK |
| 3 | TODO/FIXME/HACK/XXX críticos | ✅ OK |
| 4 | Settings de produção/staging | ✅ OK |
| 5 | Seed data (pós-fix P0) | ✅ OK |
| 6 | Worktrees / branches órfãs | ⚠️ Atenção |
| 7 | Findings abertos dos relatórios | ⚠️ Atenção (só P2/P3 de polimento) |

---

## 1. Testes + lint — ⚠️ Atenção (não bloqueia)

- **Pacotes Core** (refs/utils/offerman/stockman/craftsman/orderman/payman/guestman/doorman/
  buyman/fiscalman): todos verdes (175/98/248/226/243/289/149/389/281/9/22 passed).
- **Framework** (shop + storefront + backstage), re-rodado sem `-x` e deselecionando só os 2
  caplog conhecidos: **2883 passed, 13 skipped, 14 subtests** — exit 0. Nenhuma falha nova.
- **`make lint`**: `ruff` + Admin/Unfold canônico → **All checks passed** (exit 0).

⚠️ **Detalhe operacional:** `make test` **como está** sai com erro localmente, porque
`test-framework` roda com `-x` e o **primeiro** teste a falhar é
`test_maintenance_worker.py::test_task_failure_logs_and_cycle_continues` (um dos 2 caplog
pré-existentes). O `-x` **aborta o resto da suíte de framework** — ou seja, `make test` local
não serve hoje como gate verde ponta a ponta (storefront/backstage nem chegam a rodar). CI é
verde porque lá esses 2 testes passam. **Recomendação:** corrigir a propagação de log dos 2
testes caplog (`test_task_failure_logs_and_cycle_continues`, `test_every_task_failing_still_
completes_the_cycle`) para o `make test` voltar a ser gate local confiável. Não bloqueia staging.

## 2. Migrações pendentes — ✅ OK

`.venv/bin/python manage.py makemigrations --check --dry-run` → **"No changes detected"**.
Nenhum modelo com migração faltando. (⚠️ nota de ambiente abaixo em #6: usar sempre
`.venv/bin/python` — o `python` global do pyenv tem editable installs apontando p/ worktree
removida e nem importa `shopman.refs`.)

## 3. TODO/FIXME/HACK/XXX críticos — ✅ OK

Grep em `shopman/` + `packages/` (excluindo testes): **zero marcadores reais**. Os 2 únicos hits
(`checks.py:185,218`) são a palavra portuguesa "TODO" (=todo/qualquer), não marcador de dívida.

## 4. Settings de produção/staging — ✅ OK

`config/settings.py` é 100% env-driven, com defaults seguros:
- `DEBUG = _env_bool("DJANGO_DEBUG", False)` — default **False**.
- `SECRET_KEY` — default de dev, mas sobrescrevível por `DJANGO_SECRET_KEY`.
- `ALLOWED_HOSTS` — default `"*"` só p/ dev, sobrescrevível.

Spec de staging (`.do/app.staging-subdomains.yaml`) está endurecida:
- `DJANGO_DEBUG=false` ✅
- `DJANGO_ALLOWED_HOSTS` restrito aos domínios reais (`api./admin.staging…`) ✅
- `CSRF_TRUSTED_ORIGINS` completo p/ as 6 surfaces ✅
- `SHOPMAN_ENVIRONMENT=staging` ✅

Pontos a **confirmar** (não bloqueiam, mas ficam no radar do Pablo):
- **`.env` local tem `DJANGO_DEBUG=true`** — porém está **gitignored e não-trackeado**, então não
  vai para o staging (que usa env vars da DO). OK, mas nunca commitar `.env`.
- **`DJANGO_SECRET_KEY` não está na spec commitada** (correto: é secret gerido na app DO). Pablo
  deve **confirmar** que o secret está setado no app live — não dá para verificar pelo repo.
- **`SHOPMAN_EXPOSE_DEBUG_OTP=true` no staging** — intencional (testadores precisam ver o OTP;
  staging mantém admin/admin + PIN 1234). **Precisa ser `false` em produção.**

## 5. Seed data (pós-fix P0) — ✅ OK

`manage.py seed --flush` roda limpo (exit 0). Materializa o dataset Nelson completo, **incluindo os
Quants de produção futura-datada** que são o fix do P0 (`e6f75769`): catálogo, estoque, fidelidade,
20 templates de notificação, 5 rule configs, 2 omotenashi copies, fechamento do dia, caixas,
checklists. `✅ Seed Nelson completo!`.

## 6. Worktrees / branches órfãs — ⚠️ Atenção (não bloqueia)

3 worktrees ativas em `.claude/worktrees/`:
- `festive-lalande-b2eb39` (#61) → **0 commits à frente do main** = já mergeado ✅.
- `hungry-lalande-2fddff` → **2 commits não-mergeados**: `refactor(admin)` completando o split
  canônico (execução de produção sai do Admin) + modal de escassez p/ wrapper Unfold. É melhoria
  alinhada ao "Admin = só CRUD/config", **não blocker**. Decidir integrar antes/depois da leva.
- `design-system-sync` → **1 commit não-mergeado**: sync de design tokens do storefront
  (cosmético). Não blocker.

Higiene de ambiente (dev, não staging):
- ⚠️ **Editable installs do pyenv global apontam para worktree removida**
  (`.claude/worktrees/jovial-fermat-4052bf/packages/*`) → `python manage.py` cru quebra com
  `ModuleNotFoundError: shopman.refs`. Só `.venv/bin/python` funciona (installs corretos p/ o repo
  raiz). Footgun de dev; recomendo `pip install -e` re-apontando o env global, ou padronizar
  `.venv` em todo comando. Não afeta staging (deploy é build fresco a partir do git).
- ⚠️ **`dump.rdb`** (dump do Redis, 88 B) untracked **e não gitignored** — adicionar ao
  `.gitignore` para não vazar em commit acidental.

## 7. Findings abertos dos relatórios — ⚠️ Atenção (só polimento P2/P3)

**QA exploratório storefront (2026-07-11)** — todos os bloqueadores fechados:
- **P0** loja fechada → preorder falha 100% → ✅ `e6f75769` (fix de seed), **em main**.
- **P1 #2** money leak cupom fixo por unidade → ✅ `0f40e6cf`, **em main**.
- **P1 #3** `delivery_date` no passado aceito → ✅ `737da86e`, **em main**.
- **P1 #4** 500 por type-confusion (público + conta) → ✅ `4f791a2e`, **em main**.
- **P1 #5** rate-limit por `REMOTE_ADDR` cru → ✅ `7d4b4fdc` (XFF-aware), **em main**.
- Regressões canonizadas (`c1e75451`, `cb633fe4`), incluindo os positivos do pentest.

**Análise crítica pré-alpha (2026-07-11)** — P0s resolvidos no código vivo:
- Sweep de timezone (`date.today()`/`now().date()` → `localdate()`): **zero ocorrências no código
  vivo**. Únicos resíduos: `pickup_slots.py:44` (fallback dentro de `except`, nunca atingido com
  Django rodando) e 2 comentários explicativos no craftsman. Artefatos `build/lib/*` têm cópias
  velhas mas não são trackeados nem importados.
- `djangoProxy.ts` do storefront: cookie agora usa rest-spread (`const [name, ...valueParts] =
  pair.split('=')`) — não trunca mais valor com `=`. ✅
- Corrida Recusar × auto-confirmação: coberta pelo hardening #53–#72 (CI verde).

**Itens P2/P3 ainda abertos** (verificados; nenhum bloqueia, mas com testadores humanos alguns são
qualidade visível — vale uma faxina rápida):
- Strings em inglês na cara do cliente: `"Cart is empty."` (`views.py:74`), `"Product not found."`
  (`surface.py:616`), `"Order not found."` (payment), `"Forbidden."` (address).
- Cupom `FUNCIONARIO` aceito para não-staff (desconto 0, mas grava no carrinho sem aviso).
- `first_name`/`last_name` sem limite de tamanho nem strip de bidi (persistido, vai p/ KDS/orders).
- Oráculo de enumeração de PK de endereço (403 vs 404 distinguível) — quebra o 404 uniforme.
- Card do bundle `COMBO-PETIT-DEJ` mostra "Disponível" com componente esgotado (availability=0).
- Dialeto de erro derrapa (superset `{title}`/`{error_code}` vaza no storefront em alguns 404).
- **Nota:** o "traceback HTML do Django" citado no QA é **DEBUG-only** — em staging (`DEBUG=false`)
  vira JSON do dialeto de erro, sem vazar paths. Não é preocupação no staging.

---

## Ações recomendadas antes de abrir para humanos

Nenhuma é bloqueante; ordem de valor:

1. **Confirmar** que `DJANGO_SECRET_KEY` está setado como secret no app DO de staging (não dá p/
   ver no repo).
2. **Faxina rápida de P2** de qualidade visível: strings PT (4 lugares), cap de nome, card do
   bundle. Melhora a impressão dos testadores.
3. **Corrigir os 2 testes caplog** do `maintenance_worker` para `make test` voltar a ser gate
   verde local (hoje o `-x` mascara o resto).
4. **Higiene:** gitignore do `dump.rdb`; re-apontar editable installs do env global (ou padronizar
   `.venv`); decidir integração de `hungry-lalande` (admin split) e `design-system-sync`.

---

## Resolução (2026-07-12)

Fechados nesta passada (os demais pontos permanecem como registrado acima):

- **Item 1 / ação 3 — 2 testes caplog do `maintenance_worker`:** corrigidos. A causa era o
  `propagate=False` do logger `shopman` (config/settings.py): o handler do `caplog` vive na raiz e
  os records do worker paravam antes dela. Novo helper `_capture_worker_logs` em
  `shopman/shop/tests/test_maintenance_worker.py` anexa o handler do `caplog` direto ao logger do
  worker, capturando independente de propagação (vale igual local e CI). `make test` volta a ser
  gate verde ponta a ponta localmente.
- **Ação 4 (parcial) — `dump.rdb`:** adicionado ao `.gitignore`.
- **Ação 4 (parcial) — `.venv` canônico:** documentado em `CLAUDE.md` ("Como Rodar"): usar sempre
  `.venv/bin/python` fora do `make`; o `python` global do pyenv pode ter editable installs
  apontando para worktree removida e quebra com `ModuleNotFoundError: shopman.refs`.
