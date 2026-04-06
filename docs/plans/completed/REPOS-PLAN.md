# REPOS-PLAN — Sincronização Monorepo → Repos Individuais

## Contexto

O desenvolvimento ativo acontece no monorepo `django-shopman`. Os 8 core apps
já estão sob o namespace `shopman.*` com pyproject.toml, AppConfig e imports corretos.

Os repos individuais no GitHub (`pablondrina/django-omniman`, etc.) estão **desatualizados**:
usam namespace raiz (`omniman` em vez de `shopman.omniman`), pip package `django-omniman`
em vez de `shopman-omniman`, e estrutura de diretórios flat.

A instância Nelson vive dentro do monorepo (`shopman-app/nelson/`) e precisa de repo próprio.

### Estado atual dos repos no GitHub

| Repo GitHub | Pip package | Namespace | Status |
|---|---|---|---|
| `django-omniman` | `django-omniman 0.1.0a2` | `omniman` (flat) | desatualizado |
| `django-stockman` | `django-stockman 0.2.0` | `stockman` (flat) | desatualizado |
| `django-craftsman` | `django-craftsman 0.2.2` | `craftsman` (flat) | desatualizado |
| `django-offerman` | `django-offerman 0.3.1` | `offerman` (flat) | desatualizado |
| `django-guestman` | `django-guestman` | `guestman` (flat) | desatualizado |
| `django-doorman` | `django-doorman` | `doorman` (flat) | desatualizado |
| `django-shopman-commons` | `django-shopman-commons` | `shopman_commons` | desatualizado |
| _(não existe)_ | — | — | payman nunca publicado |
| `django-shopman` | `shopman` | `shopman` | **monorepo ativo** |

### Estado alvo

| Repo GitHub | Pip package | Namespace | Source of truth |
|---|---|---|---|
| `django-shopman` | `shopman` | `shopman` | `shopman-app/` |
| `shopman-omniman` | `shopman-omniman 0.1.0` | `shopman.omniman` | `shopman-core/omniman/` |
| `shopman-stockman` | `shopman-stockman 0.3.0` | `shopman.stockman` | `shopman-core/stockman/` |
| `shopman-craftsman` | `shopman-craftsman 0.3.0` | `shopman.craftsman` | `shopman-core/craftsman/` |
| `shopman-offerman` | `shopman-offerman 0.3.0` | `shopman.offerman` | `shopman-core/offerman/` |
| `shopman-guestman` | `shopman-guestman 0.1.0` | `shopman.guestman` | `shopman-core/guestman/` |
| `shopman-doorman` | `shopman-doorman 0.1.0` | `shopman.doorman` | `shopman-core/doorman/` |
| `shopman-payman` | `shopman-payman 0.1.0` | `shopman.payman` | `shopman-core/payman/` |
| `shopman-utils` | `shopman-utils 0.3.0` | `shopman.utils` | `shopman-core/utils/` |
| `shopman-nelson` | — (não é pip) | `nelson` | `shopman-app/nelson/` → repo próprio |

### Decisão: repos antigos

Os repos `django-*` antigos serão **arquivados** (GitHub archive) com um README
apontando para o novo repo `shopman-*`. Não serão deletados.

---

## Fase 1 — Preparar Core Apps para Push Individual (8 WPs)

Cada core app em `shopman-core/` já está pronto em termos de código e namespace.
O que falta é garantir que cada um é **self-contained** para ser pushado como
repo independente: README, LICENSE, .gitignore, test settings, CI config.

**Princípio**: o conteúdo de `shopman-core/<app>/` é a raiz do repo individual.
Tudo que está dentro é o que será pushado. Nada de fora.

---

### WP-R1: Audit — Verificar que cada core app roda isoladamente

**Status:** pendente
**Risco:** baixo — apenas verificação e fixes menores

#### Prompt

```
Execute o WP-R1 do REPOS-PLAN.md.

## Objetivo

Verificar que cada core app em shopman-core/ é self-contained e roda
seus testes isoladamente. Corrigir o que faltar.

## Para cada app (omniman, stockman, craftsman, offerman, guestman, doorman, payman, utils):

1. Verificar que existe:
   - pyproject.toml com name=shopman-<app>, namespace=shopman.<app>
   - shopman/<app>/apps.py com AppConfig.name = "shopman.<app>"
   - shopman/<app>/__init__.py
   - shopman/__init__.py (namespace package marker — pode estar vazio ou ausente)
   - <app>_test_settings.py (ou equivalente referenciado no pyproject.toml)
   - .gitignore (pelo menos __pycache__, *.egg-info, .venv, db.sqlite3)

2. Se shopman/__init__.py NÃO existe, criar vazio (necessário para namespace
   package discovery em editable installs)

3. Se .gitignore NÃO existe, criar com conteúdo padrão Python

4. Se test settings NÃO existe, verificar no pyproject.toml qual é referenciado
   e criar se necessário (copiar pattern de um que funcione)

5. Rodar `make test-<app>` para cada app e verificar que passa

## NÃO fazer:
- NÃO alterar código funcional
- NÃO mudar nomes de pacotes ou namespaces (já estão corretos)
- NÃO criar README/LICENSE ainda (WP-R2)

## Verificação
- Todos os 8 `make test-<app>` passam
- Cada app tem os arquivos mínimos listados acima
```

---

### WP-R2: Metadata — README, LICENSE, e documentação mínima

**Status:** pendente
**Risco:** zero — apenas criação de arquivos de metadados
**Depende de:** WP-R1

#### Prompt

```
Execute o WP-R2 do REPOS-PLAN.md.

## Objetivo

Cada core app precisa de README.md e LICENSE para publicação como repo
independente.

## Para cada app (omniman, stockman, craftsman, offerman, guestman, doorman, payman, utils):

1. Criar README.md na raiz do app (shopman-core/<app>/README.md) com:
   - Nome e descrição de uma linha
   - Seção "Installation": `pip install shopman-<app>`
   - Seção "Quick Start": INSTALLED_APPS config, 3 linhas de uso básico
   - Badge de versão (placeholder)
   - Link para docs no django-shopman

2. Criar LICENSE (MIT) com copyright "Pablo Valentini"

3. Atualizar pyproject.toml:
   - Garantir que readme = "README.md" está presente
   - Garantir que license = "MIT" está presente
   - Garantir que urls tem Homepage e Repository

## Modelo de README (adaptar por app):

```markdown
# shopman-<app>

<descrição de uma linha>

Part of the [Shopman](https://github.com/pablondrina/django-shopman) framework.

## Installation

pip install shopman-<app>

## Quick Start

INSTALLED_APPS = [
    "shopman.<app>",
]

## License

MIT
```

## Verificação
- Cada app tem README.md e LICENSE
- `make lint` passa
```

---

## Fase 2 — Criar Repos no GitHub e Push Inicial (9 WPs)

Push do código atual de cada app para repos novos no GitHub.
Os repos antigos (`django-*`) serão arquivados depois.

**Requer `gh` CLI autenticado.**

---

### WP-R3: Criar repos e push — Utils

**Status:** concluído
**Risco:** baixo
**Depende de:** WP-R2

#### Prompt

```
Execute o WP-R3 do REPOS-PLAN.md.

## Objetivo

Criar o repo shopman-utils no GitHub e fazer push inicial do conteúdo
de shopman-core/utils/.

## Passos

1. Criar repo no GitHub:
   gh repo create pablondrina/shopman-utils --public \
     --description "Shared utilities for the Shopman suite (monetary, phone, admin)"

2. Na pasta shopman-core/utils/:
   git init
   git remote add origin git@github.com:pablondrina/shopman-utils.git
   git add .
   git commit -m "Initial commit — shopman-utils 0.3.0"
   git push -u origin main

3. Verificar que o repo está acessível:
   gh repo view pablondrina/shopman-utils

## NÃO fazer:
- NÃO alterar o monorepo
- NÃO publicar no PyPI ainda
```

---

### WP-R4: Criar repos e push — Core Apps (7 apps)

**Status:** concluído
**Risco:** baixo
**Depende de:** WP-R3 (utils é dependência de vários)

#### Prompt

```
Execute o WP-R4 do REPOS-PLAN.md.

## Objetivo

Criar repos para os 7 core apps restantes e fazer push inicial.

## Para cada app (omniman, stockman, craftsman, offerman, guestman, doorman, payman):

1. Criar repo:
   gh repo create pablondrina/shopman-<app> --public \
     --description "<descrição curta do domínio>"

   Descrições:
   - omniman: "Omnichannel order management kernel for Django"
   - stockman: "Inventory management with quants, holds, and planning"
   - craftsman: "Production management with recipes and work orders"
   - offerman: "Product catalog with listings, collections, and bundles"
   - guestman: "Customer relationship management with loyalty and insights"
   - doorman: "OTP authentication with device trust and magic links"
   - payman: "Payment intents and transaction management"

2. Na pasta shopman-core/<app>/:
   git init
   git remote add origin git@github.com:pablondrina/shopman-<app>.git
   git add .
   git commit -m "Initial commit — shopman-<app> <version>"
   git push -u origin main

3. Verificar cada repo.

## NÃO fazer:
- NÃO alterar o monorepo
- NÃO publicar no PyPI
```

---

### WP-R5: Extrair Nelson para repo próprio

**Status:** concluído
**Risco:** médio — precisa garantir que nelson funciona standalone
**Depende de:** WP-R4

#### Prompt

```
Execute o WP-R5 do REPOS-PLAN.md.

## Objetivo

Extrair shopman-app/nelson/ para o repo shopman-nelson.

## Passos

1. Criar diretório temporário e copiar:
   - shopman-app/nelson/ → shopman-nelson/nelson/
   - Criar shopman-nelson/pyproject.toml (não é pip package, é app Django)
   - Criar shopman-nelson/README.md
   - Criar shopman-nelson/.gitignore

2. pyproject.toml mínimo:
   [project]
   name = "shopman-nelson"
   version = "0.1.0"
   description = "Nelson Boulangerie — Shopman instance"
   dependencies = [
       "shopman",
       "shopman-omniman",
       "shopman-offerman",
       "shopman-stockman",
       "shopman-craftsman",
       "shopman-guestman",
       "shopman-doorman",
       "shopman-payman",
       "shopman-utils",
   ]

3. Criar repo e push:
   gh repo create pablondrina/shopman-nelson --private \
     --description "Nelson Boulangerie — Shopman instance"
   git init && git add . && git commit -m "Initial commit" && git push

4. NÃO remover nelson/ do monorepo ainda — continua lá como referência
   até confirmarmos que o repo separado funciona.

## Verificação
- Repo criado e acessível
- README documenta como configurar
```

---

## Fase 3 — Arquivar Repos Antigos

### WP-R6: Arquivar repos django-* antigos

**Status:** pendente
**Risco:** baixo — repos ficam readonly, não são deletados
**Depende de:** WP-R4

#### Prompt

```
Execute o WP-R6 do REPOS-PLAN.md.

## Objetivo

Arquivar os repos antigos com namespace flat e adicionar README redirect.

## Para cada repo antigo:

1. Adicionar README no topo explicando a migração:

   # ⚠️ This repository has been archived

   This package has been renamed and moved to the Shopman namespace.

   **New repository:** [pablondrina/shopman-<app>](https://github.com/pablondrina/shopman-<app>)
   **New pip package:** `shopman-<app>`
   **New namespace:** `shopman.<app>`

2. Commit e push o README

3. Arquivar o repo:
   gh repo archive pablondrina/django-<app> --yes

## Repos a arquivar:
- django-omniman → shopman-omniman
- django-stockman → shopman-stockman
- django-craftsman → shopman-craftsman
- django-offerman → shopman-offerman
- django-guestman → shopman-guestman
- django-doorman → shopman-doorman
- django-shopman-commons → shopman-utils
```

---

## Fase 4 — Limpeza do Monorepo

### WP-R7: Limpar artefatos obsoletos no monorepo

**Status:** pendente
**Risco:** baixo
**Depende de:** WP-R5

#### Prompt

```
Execute o WP-R7 do REPOS-PLAN.md.

## Objetivo

Limpar artefatos obsoletos no monorepo django-shopman.

## Alterações

1. Deletar shopman-app/shopman.egg-info/ (stale, referencia shopman-ordering)

2. Deletar django-shopman-suite/ se ainda existir no dev local
   (NÃO commitar isso — é local)

3. Verificar se shopman-app/pyproject.toml lista todas as dependências
   core corretas:
   - shopman-utils>=0.3.0
   - shopman-omniman>=0.1.0
   - shopman-stockman>=0.3.0
   - shopman-craftsman>=0.3.0
   - shopman-offerman>=0.3.0
   - shopman-guestman>=0.1.0
   - shopman-doorman>=0.1.0
   - shopman-payman>=0.1.0

4. Atualizar CLAUDE.md se necessário para refletir que core apps são
   dependências pip, não subdiretórios do monorepo.

## NÃO fazer:
- NÃO remover shopman-core/ do monorepo (é onde o dev acontece)
- NÃO alterar código funcional

## Verificação
- `make test` passa
- pyproject.toml tem todas as deps
```

---

## Fase 5 — Workflow de Desenvolvimento Futuro

### WP-R8: Documentar workflow monorepo → repos

**Status:** pendente
**Risco:** zero — documentação
**Depende de:** WP-R7

#### Prompt

```
Execute o WP-R8 do REPOS-PLAN.md.

## Objetivo

Documentar o workflow de desenvolvimento para que fique claro como
manter os repos sincronizados.

## Criar docs/guides/repo-workflow.md com:

1. **Desenvolvimento diário**: acontece no monorepo django-shopman.
   Core apps em shopman-core/, framework em shopman-app/, instância
   em nelson/ (eventualmente repo separado).

2. **Publicação de core app**: quando um core app tem release:
   - Copiar shopman-core/<app>/ para o repo shopman-<app>
   - Bump version no pyproject.toml
   - Commit, tag, push
   - (Futuro: publicar no PyPI)

3. **Regra de ouro**: o monorepo é source of truth. Nunca editar
   diretamente nos repos individuais. Sempre monorepo → repo.

4. **CI futuro**: GitHub Actions nos repos individuais rodam testes
   isolados. O monorepo roda testes integrados.

## Verificação
- Documento criado e referenciado em docs/README.md
```

---

## Ordem de Execução

```
Fase 1: R1 → R2          (preparação)
Fase 2: R3 → R4 → R5     (criação de repos)
Fase 3: R6               (arquivamento)
Fase 4: R7               (limpeza)
Fase 5: R8               (documentação)
```

Total: 8 WPs. Estimativa de automação: R1-R2 são auditoria/criação de arquivos.
R3-R6 requerem `gh` CLI e acesso ao GitHub. R7-R8 são limpeza e docs.
