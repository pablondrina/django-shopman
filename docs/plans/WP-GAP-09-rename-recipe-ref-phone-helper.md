# WP-GAP-09 — Rename: `Recipe.code` → `Recipe.ref` + `_is_manychat_brazilian` → `_is_phone_brazilian`

> Housekeeping consolidando duas inconsistências de nomenclatura. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma
**Severidade**: 🟡 Baixa (consistência), mas impacto cumulativo alto (convenções ativas do projeto).

---

## Contexto

### Issue 1 — `Recipe.code` deveria ser `Recipe.ref`

`CLAUDE.md` lista exceções ao princípio "identificadores textuais usam `ref`": `Product.sku`, `Recipe.code`, `WorkOrder.code`.

Análise da exceção `Recipe.code`:
- `Recipe.code` é `SlugField(unique=True)` com valores como `croissant-v1`, `baguete-tradicional`.
- **Isso é exatamente a definição de `ref` no projeto** (slug textual, humano-legível, acoplamento frouxo via string).
- A exceção não se justifica — Recipe não tem identificador estrutural diferente; é simplesmente um slug.

Contraste legítimo: `WorkOrder.code` é sequencial auto-gerado (`WO-2026-00001`) — aí sim é estruturalmente diferente (sequencial numerado, não slug descritivo). Essa exceção permanece.

### Issue 2 — `_is_manychat_brazilian` deveria ser `_is_phone_brazilian`

Função em [packages/utils/shopman/utils/phone.py](../../packages/utils/shopman/utils/phone.py) detecta telefone BR sem código de país `55`, formato 11 dígitos com DDD prefixado com 9. O nome `_is_manychat_brazilian` amarra função a circunstância (ManyChat entrega assim) — mas a lógica testa **formato de telefone**, agnóstico ao remetente. Outro sistema que envie no mesmo formato também se beneficia.

---

## Escopo

### In

**Issue 1 — Recipe.code → Recipe.ref**:
- Rename campo em [packages/craftsman/shopman/craftsman/models/recipe.py](../../packages/craftsman/shopman/craftsman/models/recipe.py): `code` → `ref`.
- Atualizar migration inicial (projeto ainda em reset policy — CLAUDE.md permite).
- Atualizar admin craftsman + admin_unfold contrib.
- Atualizar service `CraftService` (qualquer `recipe.code` → `recipe.ref`).
- Atualizar seed de Nelson ([instances/nelson/management/commands/seed.py](../../instances/nelson/management/commands/seed.py)) — referências a receitas por code.
- Atualizar testes em `packages/craftsman/shopman/craftsman/tests/`.
- Atualizar CLAUDE.md — remover `Recipe.code` da lista de exceções.
- Atualizar [docs/reference/system-spec.md](../reference/system-spec.md) §0.3 tabela P3 + §1.4 domain model.
- Atualizar [docs/reference/glossary.md](../reference/glossary.md) se referenciar Recipe.code.

**Issue 2 — `_is_manychat_brazilian` → `_is_phone_brazilian`**:
- Rename função em [packages/utils/shopman/utils/phone.py](../../packages/utils/shopman/utils/phone.py).
- Atualizar docstring — explicar "formato 11 dígitos BR sem código de país" em vez de "bug Manychat".
- Atualizar chamadores (grep dentro de `packages/utils/`).
- Atualizar testes em `packages/utils/shopman/utils/tests/test_phone.py`.
- Atualizar [docs/reference/system-spec.md](../reference/system-spec.md) §1.1 nuance "ManyChat bug" → reformular sem depender do nome da função.

### Out

- Rename `WorkOrder.code` — **permanece exceção legítima** (sequencial auto-gerado, não slug descritivo).
- Rename `Product.sku` — **permanece exceção** (identificador universal de produto, convenção de indústria).
- Outros renames de campos do projeto.

---

## Entregáveis

- 1 PR por issue (separadas para facilitar review) OU 1 PR único nomeado `refactor(naming): Recipe.ref + phone helper rename`.
- Zero residuals: grep por `recipe.code`, `Recipe.code`, `_is_manychat_brazilian` retornam 0 matches após merge.
- Tests verdes.

---

## Invariantes a respeitar

- **Zero residuals em renames** (memória [feedback_zero_residuals.md](.claude/memory)).
- **Migrations serão resetadas** — permite editar migration inicial em vez de criar migration de rename. (Se política mudar via WP-GAP-07 antes deste merge, ajustar.)
- Tests existentes devem continuar passando com nomes novos.
- Admin forms + list_display refletem nome novo.
- Docs atualizados no mesmo PR — não deixar dangling refs.
- CLAUDE.md atualizado no mesmo PR — é convenção ativa.

---

## Critérios de aceite

1. `grep -r "Recipe.code\|\.code" packages/craftsman/` retorna apenas uses legítimos (não o campo model).
2. `grep -r "_is_manychat_brazilian" .` retorna 0 matches.
3. `make test` verde.
4. `make test-craftsman` + `make test-utils` verdes.
5. CLAUDE.md: lista de exceções contém só `Product.sku` e `WorkOrder.code` (sem Recipe).
6. system-spec.md: §0.3 tabela P3 atualizada.
7. Nelson seed funciona — `make seed` cria receitas via `ref` e roda sem erro.

---

## Referências

- [CLAUDE.md](../../CLAUDE.md) — convenção P3 atual.
- [packages/craftsman/shopman/craftsman/models/recipe.py](../../packages/craftsman/shopman/craftsman/models/recipe.py).
- [packages/utils/shopman/utils/phone.py](../../packages/utils/shopman/utils/phone.py).
- Memória [feedback_ref_not_code.md](.claude/memory).
- [docs/reference/system-spec.md §0.3, §1.1, §1.4](../reference/system-spec.md).
