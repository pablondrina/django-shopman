# Plano Temporário — Consolidação Semântica de Nomes

**Status: CANCELADO** — Decisão 2026-04-15: manter `shopman/shop/` como está. Sem rename.

~~Data: 2026-04-15~~
~~Status: Pendente (aguardando aprovação explícita do Pablo para executar — não é commit automático)~~
~~Escopo: Grande — refactor que toca imports, URLs, settings, Django label, filesystem~~
~~Arquivar em: `docs/plans/completed/` ao concluir.~~

---

## Contexto e Motivação

A Shopman Suite cresceu com três nomes que se sobrepõem semanticamente:

| Termo | Significado pretendido | Onde aparece hoje | Problema |
|---|---|---|---|
| **shop** | "a camada orquestradora" | `shopman/shop/` (folder), Django app label `shop`, `shopman.shop.*` imports | Conflita com o sentido natural de "loja". Nelson Boulangerie **é** um shop; mas `shopman.shop` é o código que orquestra Nelson, não uma loja. |
| **storefront** | "UI cliente" | URL namespace (`app_name = "storefront"`), pasta `templates/storefront/` | Correto e inequívoco. ✓ |
| **instances** | "implantações da suite" | `instances/nelson/` | Tecnicamente correto mas frio. Cada "instance" **é** um shop (uma loja real). |

O resultado é que um leitor novo no código vê `shopman/shop/` e pensa "aqui moram as lojas", quando na verdade ali mora o orquestrador — o código que **faz** as lojas funcionarem. E vê `instances/nelson/` e tem que inferir que esse é o shop Nelson.

A proposta desta consolidação é **devolver a cada nome um único significado inequívoco**.

---

## Decisão Proposta

### Vocabulário final

| Termo | Significado único | Onde vive |
|---|---|---|
| **Shopman Suite** | O projeto inteiro (packages + hub + shops) | Repo raiz `django-shopman/` |
| **Shopman** (coloquial) | A camada orquestradora — "o hub" — que compõe os Core apps em um produto utilizável | Fisicamente em `shopman/hub/` |
| **Core** (packages) | Os 8 packages pip-instaláveis (offerman, stockman, craftsman, orderman, guestman, doorman, payman, utils) | `packages/*` |
| **Shop** | Uma loja real deployada — uma instância de negócio rodando em cima da Suite | `shops/*` (ex.: `shops/nelson/`) |
| **Storefront** | A UI cliente web (uma das várias interfaces que o hub serve) | URL namespace, `templates/storefront/` |
| **POS, KDS, Dashboard, Admin** | Outras interfaces que o hub serve | Inalterado |

Ganho chave: **"shop" passa a significar exclusivamente "loja deployada"**, nunca mais "camada de código".

### Renomes físicos

| De | Para | Natureza |
|---|---|---|
| `shopman/shop/` (folder) | `shopman/hub/` | Filesystem move |
| `shopman.shop` (Python module) | `shopman.hub` | Import refactor |
| Django app label `shop` | `hub` | Config — em `apps.py`, `label = "hub"` |
| `instances/` | `shops/` | Filesystem move |
| `instances/nelson/` | `shops/nelson/` | Cai naturalmente da regra acima |

### Por que `hub` e não outras alternativas?

- **`core`** ❌ — colide com "Core apps" que já é como chamamos `packages/*` no CLAUDE.md.
- **`shopman`** (direto, sem subfolder) ❌ — colide com o namespace PEP 420 `shopman.*` usado pelos 8 packages. Teríamos `shopman/models.py` no raiz conflitando com `shopman/offerman/` etc.
- **`orchestrator`** / **`orch`** ⚠️ — descritivo mas burocrático. `shopman.orchestrator.web.views` é longo.
- **`app`** ⚠️ — genérico demais, confunde com "Django app".
- **`main`** ⚠️ — vago.
- **`hub`** ✅ — curto, evocativo ("os 8 personas se encontram no hub"), livre de colisão, natural em prosa ("o hub resolve ChannelConfig", "os handlers do hub"), casa com a metáfora de coordenação.

---

## Impacto — Mapa de Superfície

Levantamento detalhado é parte do passo 1 da execução. Estimativa inicial baseada em inspeção:

### Alto impacto (muitos arquivos, mas search/replace direto)

- **Imports Python**: `from shopman.shop.*` em todo código do hub + testes + instâncias. Estimativa: ~100-200 arquivos.
- **Settings**: `config/settings.py` — `INSTALLED_APPS`, `ROOT_URLCONF`, `TEMPLATES.DIRS`, qualquer `SHOPMAN_*` que tenha string `"shop"` hardcoded.
- **Makefile**: qualquer target que referencie `shopman.shop` ou `instances/nelson`.
- **CLAUDE.md**: atualizar toda a estrutura do projeto descrita.
- **ROADMAP.md + docs/***: atualizar menções (já tem vocabulário atualizado de 2026-04-15, mas físico ainda aponta pra `shopman/shop/`).

### Médio impacto (infra Django)

- **Django app label** `shop` → `hub`:
  - [`shopman/shop/apps.py:22`](../../shopman/shop/apps.py) `label = "shop"` → `label = "hub"`
  - `AppConfig.name` também muda: `"shopman.shop"` → `"shopman.hub"`
- **ContentTypes**: tabela `django_content_type` tem `(app_label, model)`. Não-issue porque migrations serão resetadas.
- **Permissões**: codenames `shop.add_channel`, etc. → `hub.add_channel`. Não-issue pelo mesmo motivo.
- **Migrações**: todas referenciam `app_label="shop"`. Reset completo planejado — baixo custo.

### Baixo impacto (poucos arquivos) — ótimas notícias

- **URL namespace** já é `"storefront"` em [web/urls.py:11](../../shopman/shop/web/urls.py). **Zero template precisa mudar** `{% url "storefront:..." %}`. (Verificação feita 2026-04-15: 0 ocorrências de `{% url "shop:..." %}`.)
- **ForeignKey strings** entre packages e hub: packages nunca FK pro hub (invariante ADR-001). Hub FK direto via import, não via string. Busca precisa confirmar.
- **Templates**: caminhos `templates/storefront/*.html` não mudam. ✓

### Zero impacto

- Packages (`packages/*`) não são tocados. Invariante mantida: Core é independente.
- `docs/decisions/adr-*.md` — atualizar prosa, mas o conteúdo semântico se mantém.

---

## Ordem de Execução

Cada passo deve **passar os testes** antes do próximo.

### Passo 0 — Pre-flight

- Rodar `make test` completo. Estabelecer baseline (~2448 testes).
- Branch dedicada (`refactor/naming-consolidation`) — não mexer em main.
- Confirmar que C1-C9 da leva anterior já estão mergeados.

### Passo 1 — Levantamento preciso

- Grep pra contar ocorrências reais de cada padrão antes de mexer:
  - `from shopman.shop`
  - `import shopman.shop`
  - `"shopman.shop"`
  - `"shop"` como string (app_label contexts)
  - `apps.get_app_config("shop")`
  - `instances/nelson` / `instances.nelson`
- Produzir contagem em comentário neste plano antes de seguir.

### Passo 2 — Renome filesystem do hub

- `git mv shopman/shop shopman/hub`
- Verificar que nenhum arquivo em `shopman/hub/` sub-importa algo relativo quebrado.

### Passo 3 — Search/replace de imports e strings

- `from shopman.shop` → `from shopman.hub`
- `import shopman.shop` → `import shopman.hub`
- `"shopman.shop"` → `"shopman.hub"` (INSTALLED_APPS, TEMPLATES, etc.)
- `apps.get_app_config("shop")` → `apps.get_app_config("hub")`
- Rodar `ruff check` + `python -c "import shopman.hub.lifecycle"` pra smoke-check.

### Passo 4 — Django app label

- [`shopman/hub/apps.py`](../../shopman/shop/apps.py): `name = "shopman.hub"`, `label = "hub"`
- Verificar que `ready()` ainda é chamado.
- Qualquer `shop.ModelName` string em código (FK strings, admin registrations, permission checks) → `hub.ModelName`.

### Passo 5 — Testes Passam?

- `make test` tem que passar inteiro.
- Se algum falha por label `shop` em string hardcoded, localizar e corrigir.

### Passo 6 — Renome do diretório de instâncias

- `git mv instances shops`
- Ajustar `config/settings.py` se ele aponta pra `instances.nelson.settings` ou similar (provável).
- Makefile: `make seed` deve continuar funcionando (provavelmente referencia o módulo).
- Atualizar `instances/nelson/management/commands/seed.py` se tiver imports relativos.

### Passo 7 — Docs e vocabulário

- Atualizar `CLAUDE.md` inteiro — a estrutura do projeto descrita lá é a primeira coisa que um novo Claude lê.
- Atualizar `docs/ROADMAP.md` seção Vocabulário — remover nota sobre "tensão de namespace".
- Atualizar `docs/guides/lifecycle.md` se referencia `shopman.shop` em prosa.
- Atualizar `docs/decisions/adr-001-*.md` e `adr-007-*.md` se mencionam `shopman/shop/`.
- Memória: atualizar `project_shopman_vocabulary.md` removendo a nota sobre tensão e registrando como "resolvido".

### Passo 8 — Sanidade final

- `make test` passa inteiro.
- `make lint` passa (ruff).
- `python manage.py check` passa.
- `python manage.py migrate --plan` não explode.
- Bookmarks do admin: `/admin/shop/*` → `/admin/hub/*`. Comunicar se houver usuários.
- `git grep "shopman.shop"` retorna zero.
- `git grep "instances/nelson"` retorna zero.

### Passo 9 — Commit único

- Um commit grande, atômico: `refactor(suite): consolidate naming — shopman/shop→hub, instances→shops`
- Body do commit: referenciar este plano + ADR-001 (acoplamento) + vocabulário em ROADMAP.
- Se o diff ficar imenso (~200+ arquivos), considerar 2 commits: filesystem move (1 enorme) + docs/prose (um menor). Prefiro atomicidade.

### Passo 10 — Arquivar plano

- Mover este arquivo para `docs/plans/completed/NAMING-CONSOLIDATION-PLAN.md`.
- Atualizar `docs/ROADMAP.md` removendo a entrada "pendente" e anotando "concluído".

---

## O Que NÃO Fazer

- **Não renomear packages/**. Os 8 Core apps continuam sendo `shopman.offerman`, `shopman.stockman`, etc. Eles são a identidade da Suite.
- **Não inventar features** durante o refactor. Se algo quebrar, **consertar o que quebrou**, não melhorar de passagem.
- **Não fazer no meio de uma leva de trabalho em trânsito**. Tem que estar com a árvore limpa.
- **Não tentar manter alias `shopman.shop` temporariamente** (re-export). O projeto é novo, zero consumidores externos, zero motivo pra compat shim. Feedback registrado em memória: [feedback_zero_residuals.md](../../.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/feedback_zero_residuals.md).
- **Não misturar com outro refactor** (ex.: não fazer PROTO-EXTRACTION no mesmo commit).

---

## Critério de Aprovação (antes de executar)

Pablo precisa confirmar:

1. **Nome do hub**: `hub` é a escolha? Ou prefere outro? (Candidatos rejeitados: core, shopman direto, orchestrator, app, main.)
2. **`shops/` no raiz** do repo: OK expor isso como pasta de alto nível? Alternativa: `deployments/nelson/`, `tenants/nelson/`, `sites/nelson/`. Minha preferência é `shops/` pela clareza semântica e pelo alinhamento com o novo vocabulário.
3. **Timing**: depois dos commits C1-C9 mergeados, antes ou depois de [PROTO-EXTRACTION-PLAN.md](PROTO-EXTRACTION-PLAN.md)? Não há dependência entre os dois — mas prefiro nomes consolidados **antes** da extração (porque a extração vai criar arquivos novos em `v2/` e é melhor criar já no lugar final).
4. **Label `hub` em URLs admin**: aceita que `/admin/shop/*` vire `/admin/hub/*`? Há bookmarks internos que vão quebrar?

Com essas 4 confirmações + uma janela de tempo sem trabalho em trânsito, o plano executa em 1 dia de trabalho focado (com testes rodando a cada passo).
