# WP-GAP-03 — Omotenashi como engenharia (tubulação + enforcement)

> Entrega em duas fases para realizar o corolário C4 de [docs/omotenashi.md](../omotenashi.md) e instalar mecanismos que sustentem Omotenashi no tempo. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma
**Severidade**: 🟠 Média-alta. Infraestrutura de copy centralizada existe mas 0 templates consomem — corolário C4 não cumprido. Sem enforcement automático, Omotenashi decai.

---

## Contexto

### O corolário a cumprir

De [docs/omotenashi.md](../omotenashi.md), corolário C4:

> **Copy centralizada, variável, responsável.** Strings críticas vivem em um registro único (código + admin), não espalhadas em templates. Permite revisar tom em um único ponto e impede engenheiros bem-intencionados de deslizarem para o piegas.

### O que já existe (inutilizado)

- Modelo `OmotenashiCopy` em [shopman/shop/models/omotenashi_copy.py](../../shopman/shop/models/omotenashi_copy.py) com `key`, `moment`, `audience`, `title`, `message`, `active`.
- Defaults estruturados em [shopman/shop/omotenashi/copy.py](../../shopman/shop/omotenashi/copy.py): dict `OMOTENASHI_DEFAULTS[key][moment][audience]` com strings curadas.
- Context processor `omotenashi()` registrado em [shopman/shop/context_processors.py](../../shopman/shop/context_processors.py) injetando `OmotenashiContext(QUANDO, QUEM)`.
- Admin [shopman/shop/admin/omotenashi.py](../../shopman/shop/admin/omotenashi.py): `OmotenashiCopyAdmin` com dropdowns dinâmicos, `default_preview`, action `reset_to_default`.
- Dataclass `OmotenashiContext` com resolução em cascata: DB active → `OMOTENASHI_DEFAULTS` → fallback seguro.

### Evidência do gap

Grep em `shopman/shop/templates/`:
- `{{ omotenashi[`: **0 ocorrências**.
- `{% omotenashi`: **0 ocorrências**.
- `omotenashi` em qualquer uso de template: **0 ocorrências**.

Toda a máquina existe e nada a usa. Templates seguem com strings hardcoded.

### Por que enforcement importa

O fato de o próprio autor não ter tubulado C4 é prova de que **doc sem enforcement decai**. Princípios first-class dependem de mecanismo, não de boa vontade. Este WP tubula (Fase 1) **e** protege a tubulação (Fase 2) — sem isso, qualquer dev empurra string piegas/hardcoded e Omotenashi vira decoração.

---

## Escopo

Duas fases sequenciais. Fase 2 depende de Fase 1 ter sido mergeada.

### Fase 1 — Tubulação (`{% omotenashi %}` + migração de templates)

**In**:

- Template tag `{% omotenashi <key> [moment=...] [audience=...] %}` em `shopman/shop/templatetags/omotenashi_tags.py`. Sintaxe preferencial (sobre filter) por aceitar múltiplos kwargs.
- Resolução (cascata, nunca retorna vazio):
  1. `OmotenashiCopy.objects.filter(key=key, moment=moment, audience=audience, active=True).first()` → retorna `title` + `message`.
  2. `OMOTENASHI_DEFAULTS[key][moment][audience]` — fallback estático.
  3. Fallback último: `OMOTENASHI_DEFAULTS[key]["default"]["default"]` ou string neutra pré-aprovada.
  4. Log WARNING se chegou ao fallback último.
- Inferência automática: se `moment` omitido, resolve via `OmotenashiContext.moment` do context processor. Idem para `audience`.
- Migrar strings de **5 templates core** (identificar as 3-5 strings mais load-bearing em cada):
  - [templates/storefront/home.html](../../shopman/shop/templates/storefront/home.html) — saudação + CTA temporal.
  - [templates/storefront/menu.html](../../shopman/shop/templates/storefront/menu.html) — empty state + busca.
  - [templates/storefront/cart.html](../../shopman/shop/templates/storefront/cart.html) — carrinho vazio, estoque, CTA checkout.
  - [templates/storefront/checkout.html](../../shopman/shop/templates/storefront/checkout.html) — intro + confirmação.
  - [templates/storefront/order_tracking.html](../../shopman/shop/templates/storefront/order_tracking.html) — status + agradecimento final.
- **Copy fixes específicos** (identificados em auditoria 2026-04-18):
  - Substituir "Avisamos quando chegar." por "Avisamos quando ficar pronto." (mais genérico, cobre pickup + delivery — "chegar" enviesa para delivery).
  - Grep em templates por "quando chegar" para achar todas ocorrências; migrar via `{% omotenashi "pickup_ready_notice" %}` com novo default.
- Listar strings candidatas em PR description (antes vs depois).
- Testes em `shopman/shop/tests/test_omotenashi_tag.py`:
  - Tag resolve via DB quando record active existe.
  - Fallback para defaults quando record inexistente.
  - Fallback último com log WARNING quando key desconhecida.
  - Inferência de `moment`/`audience` via context processor.
  - Reset admin action → template volta a renderizar default (integração).

**Out**:

- Migração exaustiva de **todos** os templates (admin, KDS, POS) — incremental; fica para WP sucessor.
- Novas keys/moments/audiences fora do catálogo atual — exige ADR.
- Mudança do modelo `OmotenashiCopy` — campos atuais são suficientes.
- i18n via `{% trans %}` — fora de escopo; projeto é pt-BR only.

### Fase 2 — Enforcement (lint + checklist + testes + dashboard + history)

**In**:

#### 2.1 Lint pre-commit de strings hardcoded candidatas

- Script `scripts/lint_omotenashi_copy.py` executado em pre-commit / CI.
- Detecta strings em templates que **aparentam ser user-facing copy** e não estão dentro de `{% omotenashi %}`.
- Heurísticas (imperfeitas, suficientes):
  - Strings > 3 palavras fora de `<script>`, `<style>`, `<!-- -->`, `class="..."`, `data-*="..."`.
  - Strings contendo pontuação típica de copy (`!`, `?`, `.` no meio/fim).
  - Exceções explícitas via comentário `{# copy-ok: <razão> #}` acima da linha.
- **Warning mode primeiro** (2 sprints), depois **error mode**. Não bloqueia PRs retroativamente.
- Pre-commit hook em `.pre-commit-config.yaml` (criar se não existir).

#### 2.2 Checklist PR para review de tom

- Template `.github/pull_request_template.md` (ou `docs/pull-request-checklist.md`):
  - [ ] Mudanças em copy usam `{% omotenashi %}` (ou justificativa `copy-ok`)?
  - [ ] Passa nos 5 testes de Omotenashi (invisível / antecipação / ma / calor / retorno)? Um parágrafo por teste relevante.
  - [ ] Acessibilidade: contraste AAA em primary? touch targets ≥ 48px? heading levels corretos?
  - [ ] Mobile-first: testado em 375px viewport (iPhone SE)?
  - [ ] HTMX ↔ servidor / Alpine ↔ DOM respeitado (zero `onclick`/`document.*`)?

#### 2.3 Testes automatizados dos testes objetivos

- `shopman/shop/tests/test_omotenashi_invariants.py`:
  - **Test "Invisível"**: parse templates críticos e assertar zero `onclick=`, `document.getElementById`, `classList.` (já deveria passar por convenção — safety net).
  - **Test "Ma"**: snapshot HTML de home/menu/cart; assertar densidade de elementos interativos por viewport < 8 per 1000px de scroll (threshold inicial, ajustável).
  - **Test "Antecipação"**: testar que `GET /checkout/` vindo de cliente conhecido **pré-preenche** phone, nome, endereço default (observável no response content).
- Calor e Retorno ficam em checklist manual — subjetivos demais para lint.

#### 2.4 Dashboard de saúde Omotenashi

- Widget no dashboard admin (`OmotenashiHealthWidget` no `dashboard_callback`):
  - % de templates que consomem `{% omotenashi %}` vs total user-facing (goal: > 80%).
  - Nº de `OmotenashiCopy` overrides ativos (sinal de cuidado operacional).
  - Top 5 keys mais acessadas (via middleware opcional que loga hits).
  - Últimas mudanças de copy (usa `simple-history` — item 2.5).

#### 2.5 `simple-history` em `OmotenashiCopy`

- Adicionar `HistoricalRecords()` ao modelo — toda mudança por operador é versionada.
- Admin list mostra "última mudança por X em Y" na row.

**Out** da Fase 2:

- Calor/Retorno automatizados via NLP de tom — prematuro.
- A/B testing de copy — outro eixo (feature flags).
- Teste com screen reader — manual.
- i18n.

---

## Entregáveis

### Fase 1

**Novos arquivos**:
- `shopman/shop/templatetags/__init__.py` (se não existir).
- `shopman/shop/templatetags/omotenashi_tags.py` — tag + `resolve_copy()` helper.
- `shopman/shop/tests/test_omotenashi_tag.py` — 5 casos de teste.

**Edições**:
- 5 templates listados: substituir strings hardcoded por `{% omotenashi "key" %}`.
- PR description com tabela: antes × depois × arquivo × linha.

**Nenhuma alteração em**:
- `models/omotenashi_copy.py`, `omotenashi/copy.py`, `context_processors.py`, `admin/omotenashi.py` — já funcionais.

### Fase 2

**Novos arquivos**:
- `scripts/lint_omotenashi_copy.py`.
- `.pre-commit-config.yaml` (se não existe) + hook.
- `.github/pull_request_template.md` OU `docs/pull-request-checklist.md`.
- `shopman/shop/tests/test_omotenashi_invariants.py`.

**Edições**:
- `OmotenashiCopy`: adicionar `history = HistoricalRecords()`.
- Migration correspondente.
- [shopman/shop/admin/dashboard.py](../../shopman/shop/admin/dashboard.py) (ou equivalente): incluir `OmotenashiHealthWidget`.

---

## Invariantes a respeitar

**Fase 1**:
- **Tag nunca retorna string vazia em prod**. Sempre retorna (title ou message ou fallback neutro). Fallback último → log WARNING.
- **Não adicionar copy rebuscada**: seguir tom dos defaults já aprovados — objetividade + calor + zero emoji (a não ser que o default já tenha).
- **Omotenashi C1**: "sinal de QUEM alimenta fluxo antes de gerar frase". Se audience=novo, tag pode renderizar welcome específico. Não confundir sinal com decoração.
- **`{% comment %}` multi-linha** — nunca `{# #}` multi-linha (corrompe HTML silenciosamente).
- **Tailwind classes existentes**: se novo wrapping for necessário, usar tokens já no codebase.
- **Renderização segura**: `title` e `message` passam por autoescape padrão Django.
- **Acessibilidade preservada**: heading levels, aria-labels, landmarks não quebrados pela migração.
- **Performance**: cache in-request (via `functools.lru_cache` na função de resolução OU cache com invalidação em `post_save(OmotenashiCopy)`). Documentar escolha no PR.

**Fase 2**:
- **Lint em warning mode primeiro**, error mode depois — introduzir gradualmente.
- **Checklist PR é leve** (1 minuto para preencher); se virar burocracia, é ignorado.
- **Testes objetivos não podem ser flaky** — thresholds conservadores.
- **Dashboard é read-only** — não pode introduzir nova superfície de edição.
- **Zero emoji na copy** (a não ser que default do código tenha).
- **Não adicionar libs pesadas**: heurística Python puro; testes em Django test framework padrão.

---

## Critérios de aceite

### Fase 1

1. Grep em `shopman/shop/templates/` por `{% omotenashi`: ≥ 1 ocorrência **por cada um dos 5 templates migrados**.
2. Admin altera um `OmotenashiCopy` active → refresh da página mostra nova copy (sem deploy).
3. Action `reset_to_default` → copy volta ao default imediatamente.
4. Key desconhecida no template → renderiza fallback + WARNING no log.
5. Inferência de `moment` funciona: mesmo template em hora diferente renderiza saudação diferente (manhã/tarde/noite).
6. `make test` passa com os 5 novos testes.
7. Cache: page load da home não gera > 2 queries para `OmotenashiCopy` (uma só, cached pelo resto do request).
8. Nenhum template quebra visualmente (screenshot manual antes/depois na PR).

### Fase 2

9. `lint_omotenashi_copy.py` roda em pre-commit; detecta string hardcoded candidata com > 80% recall (ajustável).
10. PR template visível em qualquer PR novo; preenchimento < 1 minuto.
11. `make test` passa com os 3 testes automatizados (Invisível/Ma/Antecipação); testes rodam em < 2s no total.
12. Admin dashboard mostra widget com % de templates usando `{% omotenashi %}`.
13. Mudança em `OmotenashiCopy` via admin aparece em history admin com diff.
14. Após 2 sprints em warning mode, lint vira error em pre-commit (PR não passa sem resolver ou justificar).
15. CLAUDE.md ou guia atualizado explicando enforcement + como adicionar `{# copy-ok: <razão> #}`.

---

## Filosofia de execução

Este WP resolve uma tensão fundamental do projeto: **princípio declarado vs prática cotidiana**. A solução **não é mais doc** (já existe 27KB lindo), é **mecanismo de baixo atrito** que torna caminho certo mais fácil que caminho errado.

Se o lint incomoda, devs ignoram. Se não incomoda, não é útil. Equilíbrio: **warning com lista clara + exceção trivial via comentário**. Cumpre Omotenashi para o próprio dev — é "invisível" até ser necessário.

---

## Referências

- [docs/omotenashi.md](../omotenashi.md) — manifesto completo (3 portões, 5 lentes, 5 testes, corolários C1-C5).
- [shopman/shop/models/omotenashi_copy.py](../../shopman/shop/models/omotenashi_copy.py).
- [shopman/shop/omotenashi/copy.py](../../shopman/shop/omotenashi/copy.py) — `OMOTENASHI_DEFAULTS` estrutura.
- [shopman/shop/context_processors.py](../../shopman/shop/context_processors.py) `omotenashi()`.
- [shopman/shop/admin/omotenashi.py](../../shopman/shop/admin/omotenashi.py).
- [docs/reference/system-spec.md §5.2](../reference/system-spec.md) — UI/UX Omotenashi.
- Memória [feedback_accessibility_omotenashi_first_class.md](.claude/memory) — convenção ativa.
