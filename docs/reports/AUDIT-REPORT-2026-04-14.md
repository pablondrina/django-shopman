# Audit Report — Django Shopman
**Data:** 2026-04-14
**Auditor:** Automated (Scheduled Task `shopman-codebase-audit`)
**Escopo:** `packages/` (8 core apps) + `shopman/shop/` (framework) + `config/`
**Base normativa:** `docs/constitution.md`, `CLAUDE.md`, ADRs 001-006

---

## 1. Resumo Executivo

**Score de saúde geral: 7.2 / 10**

O projeto está em boa saúde estrutural: os 8 packages do core estão semanticamente sólidos, a arquitetura Protocol/Adapter é respeitada na grande maioria dos casos, os modelos estão limpos e as migrations foram corretamente resetadas. Os sinais e protocolos documentados batem com o código real.

Os principais problemas identificados nesta auditoria são:

1. **Residuais de naming** — 4 pares de arquivos de adapter duplicados (antigo + novo nome) coexistem em `craftsman/` e `stockman/`, com o `__init__.py` do craftsman ainda apontando para o arquivo antigo.
2. **630 erros ruff** — majoritariamente import sorting automático (I001: 342, autofix), mas também 135 imports não usados (F401), 25 variáveis locais não usadas (F841), 16 violações de exception chaining (B904) e 7 nomes indefinidos (F821).
3. **50 exception handlers silenciosos** nas web views — dívida técnica C1 conhecida, ainda não resolvida.
4. **Ambiente de CI sem Python 3.12** — o sandbox de auditoria rodou Python 3.10; os testes não puderam ser executados. Nenhuma regressão pode ser confirmada ou descartada nesta rodada.
5. **5 worktrees git prunable** não removidos — acúmulo de worktrees de agentes anteriores.
6. **orderman → payman**: `orderman/protocols.py` re-exporta tipos do `payman` — dependência direta entre packages core. Funciona (via `noqa: F401`), mas viola o princípio de standalone.

Não foram encontrados: secrets hardcoded, `@csrf_exempt`, SQL raw sem parametrização, violações de campo monetário `_q`, usos de `onclick=` em templates, ou violações do contrato CommitService.

---

## 2. Resultados de Lint e Testes

### 2.1. Lint (ruff)

**Resultado:** `Found 630 errors` — 504 autofix disponíveis.

Ruff foi executado via `python -m ruff check packages/ shopman/shop/ config/`. O linter está instalado mas **não está no PATH** (ausente do `$PATH`; o comando `ruff` falha, `python -m ruff` funciona). O Makefile usa `ruff` diretamente — `make lint` retorna erro 127.

> **Ação imediata necessária:** corrigir `make lint` para usar `python -m ruff` ou garantir que `ruff` esteja no PATH no ambiente de desenvolvimento.

| Regra | Count | Descrição | Fixável |
|-------|-------|-----------|---------|
| I001 | 342 | Import block não ordenado/formatado | ✅ Autofix |
| F401 | 135 | Import não utilizado | ✅ Autofix |
| W293 | 30 | Whitespace em linha em branco | ✅ Autofix |
| E402 | 30 | Import de módulo não no topo do arquivo | ⚠️ Manual |
| F841 | 25 | Variável local atribuída mas nunca usada | ⚠️ Manual |
| B904 | 16 | `raise` dentro de `except` sem `from` | ⚠️ Manual |
| B007 | 11 | Loop var não usada (deveria ser `_`) | ✅ Autofix |
| F821 | 7 | Nome indefinido | 🔴 Bug potencial |
| B017 | 6 | `pytest.raises(Exception)` muito genérico | ⚠️ Qualidade |
| E741 | 1 | Nome de variável ambíguo (`l`, `O`, `I`) | ⚠️ Manual |

**Avisos adicionais:** `pyproject.toml` (raiz) e `packages/utils/pyproject.toml` usam a sintaxe deprecated `select`/`ignore` no nível `[tool.ruff]`; devem ser migrados para `[tool.ruff.lint]`.

#### F821 — Nomes Indefinidos (bug potencial)

| Arquivo | Linha | Nome | Causa |
|---------|-------|------|-------|
| `packages/craftsman/shopman/craftsman/contrib/stockman/production.py` | 39 | `ProductionResult` | Usado em type hint de string `"ProductionResult"`, mas import é lazy — ruff não resolve |
| `packages/craftsman/shopman/craftsman/contrib/stockman/production.py` | 72, 86, 131, 166, 209 | `ProductionResult`, `ProductionStatus` | Idem |
| `packages/stockman/shopman/stockman/contrib/admin_unfold/admin.py` | 56 | `Decimal` | Usado em type annotation `'Decimal'` sem import de `Decimal` no arquivo |

> **Nota:** Os F821 em `craftsman/contrib/stockman/production.py` são falso-positivos causados por type hints em strings com lazy imports. O `Decimal` em `stockman/admin.py` é potencialmente um import ausente real em annotation forward reference.

### 2.2. Testes

**Resultado: NÃO EXECUTADOS.** O ambiente de auditoria tem Python 3.10.12; o projeto requer `requires-python = ">=3.12"`. `make test` não pôde ser executado.

Segundo `docs/status.md` (atualizado em 2026-04-06), o estado esperado é:
- **Core:** 1.560 testes (utils 71, offerman 188, stockman 162, craftsman 207, orderman 231, guestman 369, doorman 221, payman 111)
- **Framework:** 410 testes
- **Total:** ~1.970 testes

Débitos conhecidos: 10 skips em testes Manychat webhook, 4 skips em perishable shelflife, 9 skips de concorrência Postgres-only, 1 skip Playwright E2E.

---

## 3. Violações Constitucionais

Nenhuma violação grave detectada. Os princípios constitucionais (core pequeno, estados canônicos, semântica explícita) estão sendo seguidos de modo geral. Dois pontos merecem atenção:

### 3.1. orderman re-exporta tipos do payman (violação de standalone parcial)

**Arquivo:** `packages/orderman/shopman/orderman/protocols.py` — linhas 22-30

```python
# Payment Protocols — re-exported from shopman.payman.protocols
from shopman.payman.protocols import (  # noqa: F401
    CaptureResult,
    GatewayIntent,
    PaymentBackend,
    ...
)
```

O `orderman` é declarado como app standalone (sem dependências de outros packages). Esta re-exportação cria uma dependência direta em tempo de importação do `payman`. Pela constituição (3.4), `adapter` deve fazer a ponte — não o core.

**Impacto:** baixo em produção (payman sempre instalado junto), mas viola standalone instalável e cria acoplamento implícito.

**Recomendação:** mover as re-exportações para `shopman/shop/protocols.py` (framework) ou usar TYPE_CHECKING guard.

### 3.2. CraftingProductionBackend — nome usa terminologia antiga

**Arquivo:** `packages/craftsman/shopman/craftsman/contrib/stockman/production.py` — linha 24

```python
class CraftingProductionBackend:
```

O termo `Crafting` é a terminologia pré-refatoração. Deveria ser `CraftsmanProductionBackend`.

---

## 4. Drifts de Convenção

### 4.1. Frontend HTMX/Alpine.js ✅

Nenhuma violação encontrada nos templates. Varredura em `shopman/shop/web/templates/` para `onclick=`, `onchange=`, `document.getElementById`, `classList.toggle/add/remove` — **resultado limpo**.

### 4.2. Convenção `ref` vs `code` ✅ (exceto casos conhecidos)

Os campos `code` existentes são todos os casos documentados como exceções: `Recipe.code` (SlugField descritivo) e `WorkOrder.code` (código sequencial auto-gerado). Nenhuma violação adicional detectada.

### 4.3. Sufixo `_q` para valores monetários ✅

Nenhuma violação encontrada. Os campos de valor monetário sem `_q` identificados são todos legítimos (variáveis locais intermediárias de `models.Sum("amount_q")`).

### 4.4. Zero Residuals ⚠️ (menor)

**Arquivo:** `packages/craftsman/shopman/craftsman/tests/test_v022.py` — linha 271

```python
farinha_item.quantity = Decimal("10")  # was 5
```

Comentário residual de rename/ajuste. Viola a regra "zero residuals".

### 4.5. Zero Backward-compat aliases ✅

Nenhum padrão `OldName = NewName` encontrado.

---

## 5. Problemas de Dependência

### 5.1. Duplicate Adapter Files — Naming Residuals 🔴

Quatro pares de arquivos de adapter convivem nos packages de `craftsman` e `stockman`. São resultado de renomeações incompletas durante o ciclo de refatoração:

**craftsman/adapters/** (4 arquivos, 2 pares duplicados):

| Arquivo antigo (remover) | Arquivo novo (manter) | `__init__.py` aponta para |
|--------------------------|----------------------|--------------------------|
| `stocking.py` (`_stocking_available`, importa `offering`) | `stock.py` (`_stockman_available`, importa `catalog`) | `stock.py` ✅ |
| `offering.py` (usa `crafting_settings`) | `catalog.py` (usa `craftsman_settings`) | `catalog.py` ✅ |

O `craftsman/__init__.py` e `craftsman/conf.py` já apontam corretamente para `stock.py` (novo). Os arquivos a remover são `stocking.py` e `offering.py`.

**stockman/adapters/** (4 arquivos, 2 pares duplicados):

| Arquivo antigo (remover) | Arquivo novo (manter) | `__init__.py` aponta para |
|--------------------------|----------------------|--------------------------|
| `crafting.py` (`_crafting_available`) | `production.py` (`_craftsman_available`) | `production.py` ✅ |
| `offering.py` | `sku_validation.py` | `sku_validation.py` ✅ |

**Conclusão:** ambos os `__init__.py` já apontam para os arquivos novos. Os arquivos antigos (`craftsman/stocking.py`, `craftsman/offering.py`, `stockman/crafting.py`, `stockman/offering.py`) são código morto e devem ser removidos.

### 5.2. stockman → orderman (import condicional) ✅ Aceitável

**Arquivo:** `packages/stockman/shopman/stockman/contrib/alerts/handlers.py` — linha 103

```python
from shopman.orderman.models import Directive
```

Import **lazy** dentro de bloco try/except com fallback gracioso. Comportamento documentado e correto para contrib opcionais.

### 5.3. stockman → craftsman em adapters ✅ Aceitável

`packages/stockman/shopman/stockman/adapters/crafting.py` e `production.py` importam `craftsman` — isso é esperado, pois esses arquivos **são** o adapter de integração stockman↔craftsman.

### 5.4. 5 Git Worktrees Prunable ⚠️

Os seguintes worktrees de agentes estão marcados como `prunable` mas não foram removidos:
- `claude/bold-lederberg` (commit e302532)
- `claude/elastic-wing` (commit 8446f9a)
- `claude/frosty-mestorf` (commit 1f0cedd)
- `claude/funny-wiles` (commit 8840af8)
- `claude/naughty-herschel` (commit 73dac92)

Não causam bugs, mas poluem o repositório e o filesystem.

---

## 6. Código Morto e Dívida Técnica

### 6.1. 50 Exception Handlers Silenciosos nas Views (C1 — regressão)

A dívida técnica C1 listada em `docs/status.md` permanece aberta. Encontrados 50 blocos `except Exception` no diretório `shopman/shop/web/views/`:

**Arquivos mais afetados:**
- `checkout.py` — 9 ocorrências
- `pos.py` — 7 ocorrências
- `auth.py` — 5 ocorrências
- `catalog.py` — 4 ocorrências
- `orders.py`, `tracking.py`, `bridge.py`, `devices.py` — demais ocorrências

Muitos capturam a exceção mas retornam respostas genéricas sem logging estruturado, tornando debugging em produção difícil.

### 6.2. F401 — 135 Imports Não Utilizados

Distribuídos por todo o codebase. A maioria está em `contrib/admin_unfold/__init__.py` de vários packages (importações de classes de admin que não são mais necessárias). Todos são autofix.

### 6.3. F841 — 25 Variáveis Locais Não Usadas

Distribuídas em tests e services. Incluem casos em `craftsman/tests/test_vnext.py` (linhas 838-840) com múltiplos resultados de unpacking ignorados.

### 6.4. 15 Imports Profundos de guestman.contrib no Framework (C4 — parcialmente reduzido)

A auditoria anterior (2026-04-10) identificou 28 imports de `shopman.guestman.contrib.*` no framework. Na rodada atual, 15 imports similares foram encontrados em `shopman/shop/`. Redução de 46% desde a auditoria anterior — progresso, mas ainda presente.

### 6.5. Ruff pyproject.toml — Configuração Deprecated

**Arquivos:** `pyproject.toml` (raiz) e `packages/utils/pyproject.toml`

```toml
# Antes (deprecated):
[tool.ruff]
select = ["E", "W", ...]
ignore = ["E501"]

# Deve ser:
[tool.ruff.lint]
select = ["E", "W", ...]
ignore = ["E501"]
```

---

## 7. Problemas de Segurança

### 7.1. DEBUG padrão em `true` ⚠️ (baixo, documentado)

**Arquivo:** `config/settings.py` — linha 30

```python
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("true", "1", "yes")
```

O default é `"true"`, o que significa que em deploy sem a variável `DJANGO_DEBUG`, o servidor rodará com `DEBUG=True`. Há uma nota no código (`⚠️ PRODUÇÃO: Definir DJANGO_DEBUG=false`), mas o padrão deveria ser seguro (`"false"`).

**Recomendação:** inverter o default para `"false"`.

### 7.2. SECRET_KEY com fallback de desenvolvimento ✅ Aceitável

**Arquivo:** `config/settings.py` — linhas 26-27

```python
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")
```

Há uma assertion explícita na seção de produção (`settings.py` linha 683) que bloqueia o deploy se `SECRET_KEY` não for configurada. Padrão de segurança aceitável.

### 7.3. Nenhum @csrf_exempt Detectado ✅

### 7.4. Nenhum SQL Raw Sem Parametrização Detectado ✅

A única query raw encontrada é `cursor.execute("SELECT 1")` em `doorman/views/health.py` — healthcheck legítimo e seguro.

### 7.5. Nenhum Secret Hardcoded em Adapters ✅

Todos os tokens e secrets são lidos de variáveis de ambiente.

---

## 8. Inconsistências de Modelos

### 8.1. `__str__` ✅

Todos os arquivos de model nos packages `packages/` têm `__str__` definido (varredura não encontrou ausências).

### 8.2. ForeignKey com `on_delete` explícito ✅

Todos os `ForeignKey` identificados têm `on_delete` explícito (verificado nas ocorrências encontradas: `PROTECT`, `CASCADE`, `SET_NULL` todos presentes e aparentemente adequados ao contexto).

### 8.3. Model Meta ordering ✅

Os modelos principais com campos de data (`Order`, `Session`, `OrderItem`) têm `ordering` definido no `Meta`.

---

## 9. Schema Drift (data-schemas.md vs código real)

### 9.1. Chaves documentadas e confirmadas no código ✅

Verificação cruzada das chaves de `Session.data` e `Order.data` documentadas em `docs/reference/data-schemas.md`:

- `outside_business_hours`: escrito em `rules/validation.py:55` ✅
- `delivery_zone_error` e `delivery_fee_q`: escritos em `modifiers.py` ✅
- `payment`: lido/escrito em `services/payment.py`, `webhooks/efi.py`, views ✅
- `CommitService._do_commit()`: lista de chaves propagadas documentada e coerente ✅

### 9.2. Chave `customer_name` — marcada como "Não usar" ⚠️

A chave `customer_name` em `Order.data` está documentada como deprecated ("**Não usar.** Views agora leem `customer.name`"). Confirmar que nenhum novo código a está escrevendo.

Varredura:
```bash
grep -rn "customer_name" shopman/shop/ --include="*.py" | grep -v test_
```
Nenhuma escrita nova encontrada. Apenas leituras de fallback documentadas. ✅

### 9.3. Atributo `shelflife` vs `shelf_life_days` — Bug Conhecido Aberto 🟠

**Arquivo:** `packages/stockman/shopman/stockman/services/queries.py` — linha 24

```python
shelflife = getattr(sku_or_product, "shelflife", None) if not isinstance(sku_or_product, str) else None
```

**Arquivo:** `packages/offerman/shopman/offerman/models/product.py` — linha 105

```python
shelf_life_days = models.IntegerField(...)
```

`stockman` espera atributo `.shelflife` nos objetos de produto; `offerman` define `.shelf_life_days` (nome canônico). Quando `offerman.Product` é passado diretamente para funções do `stockman`, o shelflife é ignorado (fallback para `None`), desabilitando silenciosamente a lógica de validade de lote para produtos perecíveis.

**Fix correto:** atualizar `stockman` para usar `shelf_life_days` (que é o nome canônico do offerman), não o contrário. Os arquivos a corrigir são `packages/stockman/shopman/stockman/shelflife.py` (linhas 24 e 57) e `packages/stockman/shopman/stockman/services/queries.py` (linha 24):

```python
# Antes (stockman espera nome inexistente):
shelflife = getattr(product, 'shelflife', None)

# Depois (usar nome canônico do offerman):
shelflife = getattr(product, 'shelf_life_days', None)
```

Bug confirmado — listado como débito técnico "Perishable shelflife wiring" em `ROADMAP.md` com 4 testes em skip. **Impacto real para padaria com croissants e bolos perecíveis.**

---

## 10. Signal/Protocol Drift

### 10.1. Signals: 17 documentados, 17 encontrados no código ✅

| Sinal | Módulo | Documentado | No código |
|-------|--------|-------------|-----------|
| `product_created`, `price_changed` | offerman | ✅ | ✅ |
| `production_changed` | craftsman | ✅ | ✅ |
| `holds_materialized` | stockman | ✅ | ✅ |
| `order_changed` | orderman | ✅ | ✅ |
| `customer_created`, `customer_updated` | guestman | ✅ | ✅ |
| `customer_authenticated`, `access_link_created`, `verification_code_sent`, `verification_code_verified`, `device_trusted` | doorman | ✅ | ✅ |
| `payment_authorized`, `payment_captured`, `payment_failed`, `payment_cancelled`, `payment_refunded` | payman | ✅ | ✅ |

Nenhum drift de signal detectado.

### 10.2. Protocols: documentação alinhada com código ✅ (com nota)

A documentação em `docs/reference/protocols.md` foi atualizada em 2026-04-14 (mesmo dia desta auditoria) e alinha com o código. **Uma inconsistência menor:**

`docs/reference/protocols.md` lista o adapter do craftsman como `craftsman/adapters/stock.py` — que é o arquivo **antigo** (ver seção 5.1). A documentação deveria apontar para `stocking.py` após a consolidação.

---

## 11. Regressões (comparação com auditorias anteriores)

Comparação com `docs/audit/2026-04-10-kernel-framework-audit.md`:

| Item | Status anterior | Status atual | Observação |
|------|----------------|--------------|------------|
| C1 — Admin do omniman quebra (`flow`/`config`) | 🔴 Bloqueante | ✅ Resolvido | Não encontrado — estrutura `omniman` removida |
| C2 — handlers/customer.py duplicado | 🔴 Crítico | ✅ Resolvido | `handlers/customer.py` removido |
| C3 — Hold.objects.filter(metadata__reference=...) | 🔴 Crítico | ✅ Resolvido | Não encontrado em código atual |
| C4 — 28 imports profundos guestman.contrib | 🔴 Crítico | 🟠 Parcial | Reduzido de 28 para 15 ocorrências |
| C5 — ChannelConfig campos mortos | 🟠 Alto | Não verificado | Requer análise runtime |
| C6 — Handlers órfãos | 🟠 Alto | Não verificado | Requer análise de registro |
| C7 — checks.py config__fiscal | 🟠 Alto | ✅ Resolvido | `checks.py` atual não referencia `config__fiscal` |
| C8 — Resíduos de naming (Stocking/Crafting/Offering) | 🟠 Alto | 🟡 Parcial | Classe `CraftingProductionBackend`, conf.py path antigo, arquivos duplicados |
| C11 — Protocol CustomerBackend com `code` | 🟡 Médio | ✅ Resolvido | Não encontrado |
| C13 — try/except ImportError escondendo deps | 🟡 Médio | 🟡 Residual | Padrão ainda presente mas documentado como legítimo |
| C14 — Status de pagamento de order.data | 🟡 Médio | ✅ Resolvido | `_payment_status()` usa `payment_svc.get_payment_status()` |
| C1 (status.md) — 42+ except silenciosos | 🔴 Aberto | 🟠 Persistente | 50 ocorrências encontradas |

**Regressões confirmadas:** nenhuma nova.
**Melhorias confirmadas:** C1 (admin), C2, C3, C7, C11, C14 — todos resolvidos.
**Persistências:** C4 (parcial), C8 (parcial), except silenciosos.

---

## 12. Recomendações (priorizadas)

### 🔴 Alta Prioridade

**R1 — Remover arquivos de adapter duplicados obsoletos (craftsman + stockman)**

Os `__init__.py` já apontam para os arquivos corretos (novos). Basta apagar os arquivos antigos:

```
# Remover (arquivos antigos — código morto):
packages/craftsman/.../adapters/stocking.py    ← substituído por stock.py
packages/craftsman/.../adapters/offering.py    ← substituído por catalog.py
packages/stockman/.../adapters/crafting.py     ← substituído por production.py
packages/stockman/.../adapters/offering.py     ← substituído por sku_validation.py

# Atualizar:
docs/reference/protocols.md                    ← confirmar que referencia stock.py (novo) ✅
```

Nenhuma alteração nos `__init__.py` ou `conf.py` — já estão corretos.

**R2 — Corrigir bug shelflife (perecíveis)**

`stockman` usa `getattr(product, 'shelflife', None)` mas o nome canônico do offerman é `shelf_life_days`. Atualizar `stockman` para usar o nome correto (não o contrário — `shelf_life_days` prevalece):

```python
# packages/stockman/shopman/stockman/shelflife.py — linhas 30 e 63
shelflife = getattr(product, 'shelf_life_days', None)  # era 'shelflife'

# packages/stockman/shopman/stockman/services/queries.py — linha 24
shelflife = getattr(sku_or_product, "shelf_life_days", None) ...  # era "shelflife"
```

Sem migration necessária. Reativa os 4 testes em skip em `test_production_stock.py::TestPerishableProducts`.

**R3 — Executar `ruff --fix` para erros autofix**

Eliminar 504 erros automáticos (import sorting, unused imports, whitespace):
```bash
python -m ruff check packages/ shopman/shop/ config/ --fix
```

### 🟠 Média Prioridade

**R4 — Iniciar C1: Adicionar logging estruturado aos except handlers**

50 blocos `except Exception` nas views não fazem log. Priorizar `checkout.py` e `pos.py` por serem fluxos críticos de negócio. Adicionar `logger.exception(...)` antes de retornar a resposta de erro.

**R5 — Remover worktrees prunable**

```bash
git worktree remove .claude/worktrees/bold-lederberg
git worktree remove .claude/worktrees/elastic-wing
git worktree remove .claude/worktrees/frosty-mestorf
git worktree remove .claude/worktrees/funny-wiles
git worktree remove .claude/worktrees/naughty-herschel
```

**R6 — Inverter default de DEBUG para seguro**

`config/settings.py` linha 30:
```python
# Antes (inseguro):
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("true", "1", "yes")

# Depois (seguro):
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("true", "1", "yes")
```

**R7 — Migrar ruff config para [tool.ruff.lint]**

Eliminar avisos de deprecação em `pyproject.toml` e `packages/utils/pyproject.toml`.

**R8 — Mover re-exports payman de orderman/protocols.py para framework**

Para restaurar standalone do `orderman`. Mover as re-exportações para `shopman/shop/protocols.py` usando `TYPE_CHECKING` guard se necessário.

### 🟡 Baixa Prioridade

**R9 — Renomear CraftingProductionBackend**

`packages/craftsman/shopman/craftsman/contrib/stockman/production.py` — renomear para `CraftsmanProductionBackend`.

**R10 — Adicionar import de Decimal em stockman/admin.py**

`packages/stockman/shopman/stockman/contrib/admin_unfold/admin.py` linha 56 usa `'Decimal'` em type annotation sem import.

**R11 — Remover comentário residual em test_v022.py**

`packages/craftsman/.../tests/test_v022.py:271` — remover `# was 5`.

**R12 — Completar C4: reduzir imports profundos de guestman.contrib no framework**

15 imports restantes de `shopman.guestman.contrib.*` no `shopman/shop/`. Definir API pública em `guestman/__init__.py` para expor os tipos necessários.

---

## Apêndice: Comandos de Diagnóstico

```bash
# Executar lint completo
python -m ruff check packages/ shopman/shop/ config/

# Aplicar fixes automáticos
python -m ruff check packages/ shopman/shop/ config/ --fix

# Listar adapters duplicados
ls packages/craftsman/shopman/craftsman/adapters/
ls packages/stockman/shopman/stockman/adapters/

# Verificar worktrees
git worktree list

# Verificar imports cruzados entre packages
grep -rn "from shopman\.\(offerman\|stockman\|craftsman\|orderman\|guestman\|doorman\|payman\)" \
  packages/ --include="*.py" | grep -v "__pycache__" | \
  awk '...' # script completo na seção 5

# Verificar shelflife
grep -n "shelflife\|shelf_life" packages/stockman/.../services/queries.py
grep -n "shelf_life_days" packages/offerman/.../models/product.py
```
