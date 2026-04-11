# DRIFT-FIX-PLAN-2 — Correções pós-audit 2026-04-09

**Origem:** `docs/_inbox/audit_drift_scan_2026-04-09.md`
**Data:** 2026-04-09
**Total de achados:** 17 (3 críticos, 5 altos, 5 médios, 4 baixos)

Cada WP abaixo é autocontido: inclui contexto, diagnóstico, solução, arquivos e critério de conclusão.
Execute na ordem listada. DS-1, DS-2, DS-3 e DS-4 são independentes entre si e podem rodar em paralelo.

| WP | Escopo | Severity |
|---|---|---|
| **DS-1** | Fiscal topics mismatch + mock backends em produção | Crítico |
| **DS-2** | `order_id` (PK) → `order_ref` no CommitService e API | Crítico |
| **DS-3** | Resíduos de `"pipeline"` em channel.py + admin | Alto |
| **DS-4** | `kds.py` não lê `fulfillment_type` | Alto |
| **DS-5** | `data-schemas.md` — documentar chaves ausentes e corrigir `intent_id` | Alto |
| **DS-6** | Completar AF-4: `ChannelConfig.effective()` no CommitService | Médio |
| **DS-7** | Consistência: topics + `session_key` + nomes antigos de persona | Médio |
| **DS-8** | Feature: label configurável para `handle_type`/`handle_ref` via Admin | Feature |
| **DS-9** | Fixes menores: concorrência em `emit_event`, `DEFAULT_DDD`, offline.html | Baixo |

---

## WP-DS-1 — Fiscal topics mismatch + mock backends em produção

**Gravidade:** crítica. Toda emissão de NF-e falha silenciosamente; mocks de teste são carregados em produção se backend não estiver configurado.

### Diagnóstico

**Problema 1 — Mismatch de tópicos:**
`framework/shopman/services/fiscal.py` cria Directives com strings literais:
- linha 34: `directives.queue("fiscal.emit", order, ...)`
- linha 62: `directives.queue("fiscal.cancel", order, ...)`

Os handlers registrados em `framework/shopman/setup.py` e `framework/shopman/handlers/fiscal.py` escutam:
- `FISCAL_EMIT_NFCE = "fiscal.emit_nfce"` (de `topics.py`)
- `FISCAL_CANCEL_NFCE = "fiscal.cancel_nfce"` (de `topics.py`)

Resultado: nenhuma Directive fiscal jamais é processada. Ficam `queued` para sempre.

**Problema 2 — Mock backends em produção:**
`framework/shopman/setup.py:248-268`, funções `_load_fiscal_backend()` e `_load_accounting_backend()`:
```python
# setup.py:248-252
if not backend_path:
    try:
        from shopman.tests._mocks.fiscal_mock import MockFiscalBackend
        return MockFiscalBackend()
    except ImportError:
        return None
```
Quando `SHOPMAN_FISCAL_BACKEND` não está configurado, importa e instancia `MockFiscalBackend` e `MockAccountingBackend` de `shopman.tests._mocks`. Ausência de configuração no deploy = mocks ativos em produção silenciosamente.

### Solução

**Fix 1:** Em `services/fiscal.py`, substituir strings literais pelos imports de `topics.py`:
```python
from shopman.topics import FISCAL_EMIT_NFCE, FISCAL_CANCEL_NFCE

# linha 34
directives.queue(FISCAL_EMIT_NFCE, order, ...)
# linha 62
directives.queue(FISCAL_CANCEL_NFCE, order, ...)
```

**Fix 2:** Em `setup.py`, remover os blocos `try/except Import` que carregam mocks como fallback. Quando backend não configurado, retornar `None` imediatamente (comportamento já existente quando ImportError ocorre):
```python
def _load_fiscal_backend():
    backend_path = getattr(settings, "SHOPMAN_FISCAL_BACKEND", None)
    if not backend_path:
        return None  # ← sem fallback para mock
    return import_string(backend_path)()
```
Mock deve ser configurado explicitamente via `settings.SHOPMAN_FISCAL_BACKEND = "shopman.tests._mocks.fiscal_mock.MockFiscalBackend"` nos settings de desenvolvimento/teste.

Verificar se `settings/test.py` ou `conftest.py` já configura isso explicitamente. Se não, adicionar.

### Arquivos a modificar

- `framework/shopman/services/fiscal.py` — importar constantes de `topics.py` e substituir strings literais.
- `framework/shopman/setup.py` — remover fallback para mock backends em `_load_fiscal_backend` e `_load_accounting_backend`.
- `project/settings.py` ou `instances/nelson/settings.py` — verificar se `SHOPMAN_FISCAL_BACKEND` está configurado para dev/prod.
- Testes existentes de fiscal — confirmar que `conftest.py` configura o backend mock via settings.

### Critério de conclusão

- [ ] `grep -rn '"fiscal.emit"' framework/shopman/services/` retorna zero.
- [ ] `grep -rn '"fiscal.cancel"' framework/shopman/services/` retorna zero.
- [ ] `setup.py` não importa nada de `shopman.tests._mocks` fora de um bloco condicional de test/debug.
- [ ] `settings.py` de desenvolvimento/test tem `SHOPMAN_FISCAL_BACKEND` explicitamente configurado (ou `None`).
- [ ] `make test` verde.

---

## WP-DS-2 — `order_id` (PK interna) → `order_ref` no CommitService e API

**Gravidade:** crítica. PK sequencial interna exposta via API. Viola convenção `ref` e revela volume de pedidos.

### Diagnóstico

`packages/orderman/shopman/orderman/services/commit.py:388-394`:
```python
return {
    "order_ref": order.ref,
    "order_id": order.pk,   # ← PK interna, sequencial, exposta
    "session_key": session.session_key,
    ...
}
```

`framework/shopman/api/serializers.py:45`:
```python
order_id = serializers.IntegerField()   # ← expõe PK na API REST
```

`framework/shopman/api/views.py:219` e demais consumers do dict de retorno de `CommitService`.

A convenção do projeto é `ref` para identificadores externos. `order.pk` é detalhe de implementação do banco, não deve sair do repositório.

O usuário confirmou: **`order_ref` é o identificador canônico**. Remover `order_id` completamente.

### Solução

1. Em `commit.py`, remover `"order_id": order.pk` do dict de retorno de `_do_commit()`.
2. Em `api/serializers.py`, remover `order_id = serializers.IntegerField()`.
3. Auditar todos os callers de `CommitService` que possam usar `result["order_id"]`:
   - `framework/shopman/web/views/checkout.py`
   - `framework/shopman/api/views.py`
   - `framework/shopman/flows.py`
   - Qualquer outro que capture o retorno de `commit_service.commit(...)`
4. Onde o PK é realmente necessário (improvável, mas verificar), obter via `Order.objects.get(ref=order_ref).pk`.

### Arquivos a modificar

- `packages/orderman/shopman/orderman/services/commit.py` — remover `"order_id"` do retorno.
- `framework/shopman/api/serializers.py` — remover campo `order_id`.
- `framework/shopman/api/views.py` — remover qualquer referência a `order_id` no retorno de commit.
- `framework/shopman/web/views/checkout.py` — verificar se usa `result["order_id"]`.
- Qualquer template ou JavaScript que acesse `order_id` da resposta da API.

### Critério de conclusão

- [ ] `grep -rn '"order_id"' framework/ packages/` retorna zero (exceto comentários explicativos e testes que verificam ausência).
- [ ] API de commit retorna apenas `order_ref` como identificador do pedido criado.
- [ ] `make test` verde.

---

## WP-DS-3 — Resíduos de `"pipeline"` em channel.py e admin Orderman

**Gravidade:** alta. Admin exibe e aceita configuração de `pipeline` que não tem efeito — operadores que confiam no admin ficam com configuração silenciosamente ignorada.

### Diagnóstico

AF-3 removeu `Pipeline` do `ChannelConfig`, mas três resíduos permanecem:

**Resíduo 1 — `KNOWN_CONFIG_KEYS`:**
`packages/orderman/shopman/orderman/models/channel.py:11`:
```python
KNOWN_CONFIG_KEYS = frozenset({
    "confirmation", "payment", "stock", "pipeline",  # ← "pipeline" inválido
    "notifications", "rules", "flow"
})
```
O método `Channel.clean()` usa esse set para validar o JSON. `"pipeline"` passa sem warning.

**Resíduo 2 — Admin:**
`packages/orderman/shopman/orderman/admin.py:250-256`:
```python
pipeline = c.get("pipeline", {})
on_commit = pipeline.get("on_commit", [])
on_confirmed = pipeline.get("on_confirmed", [])
```
O admin exibe uma seção "Pipeline" lendo dados de `channel.config["pipeline"]`, que não tem mais efeito.

**Resíduo 3 — Docstring/help_text:**
`packages/orderman/shopman/orderman/models/channel.py:22-23,70`:
```python
# channel.py:22-23
Config segue o schema do ChannelConfig dataclass (7 aspectos):
confirmation, payment, stock, pipeline, notifications, rules, flow.
# channel.py:70 (help_text)
"pipeline {on_commit, on_confirmed, on_cancelled, ...} (listas de topics), "
```

### Solução

1. Remover `"pipeline"` de `KNOWN_CONFIG_KEYS` em `channel.py`.
2. Em `admin.py`, remover a leitura de `c.get("pipeline", {})` e a exibição da seção de pipeline. Verificar onde `on_commit`/`on_confirmed` são realmente configurados hoje (provavelmente em `ChannelConfig.Flow.auto_transitions`) e atualizar a exibição do admin para refletir a estrutura real.
3. Atualizar docstring e `help_text` de `Channel` para listar os 6 aspectos reais: `confirmation, payment, stock, notifications, rules, flow` (7 → 6).
4. Verificar se algum canal existente nos dados de seed ou instâncias tem `"pipeline"` no JSON. Se sim, remover essas chaves do seed.

### Arquivos a modificar

- `packages/orderman/shopman/orderman/models/channel.py` — `KNOWN_CONFIG_KEYS`, docstring, help_text.
- `packages/orderman/shopman/orderman/admin.py` — remover seção pipeline.
- `framework/shopman/management/commands/seed.py` — verificar e remover `"pipeline"` de configs de canal.
- `instances/nelson/` — verificar fixtures/configs.

### Critério de conclusão

- [ ] `grep -rn '"pipeline"' packages/orderman/` retorna zero (exceto testes de migração se existirem).
- [ ] Admin de Channel não exibe mais seção "Pipeline".
- [ ] Docstring de `Channel` lista 6 aspectos (sem `pipeline`).
- [ ] `make test` verde.

---

## WP-DS-4 — `kds.py` não lê `fulfillment_type`

**Gravidade:** alta. KDS exibe string vazia para tipo de entrega em pedidos do storefront.

### Diagnóstico

`framework/shopman/web/views/pedidos.py:63` faz o fallback correto:
```python
ft = order.data.get("fulfillment_type") or order.data.get("delivery_method", "")
```

`framework/shopman/web/views/kds.py:42,118` lê apenas a chave legada:
```python
# kds.py:42
delivery_method = order.data.get("delivery_method", "")
# kds.py:118 — idem
```

`data-schemas.md` documenta `fulfillment_type` como chave canônica escrita pelo checkout padrão do storefront, e `delivery_method` como legada. KDS silenciosamente exibe `""` para todos os pedidos web.

### Solução

**Opção A (recomendada):** Criar helper centralizado em `framework/shopman/services/order_helpers.py` (ou módulo equivalente):
```python
def get_fulfillment_type(order) -> str:
    """Retorna o tipo de fulfillment do pedido, com fallback para chave legada."""
    return (
        order.data.get("fulfillment_type")
        or order.data.get("delivery_method", "")
    )
```
Atualizar `kds.py` e `pedidos.py` para usar o helper. Assim a lógica de fallback fica em um só lugar.

**Opção B (mínima):** Replicar o fallback do `pedidos.py` no `kds.py` (todas as ocorrências: linhas 42 e 118).

Prefira Opção A — evita duplicação e consolida a lógica de migração de chave em um único ponto.

Leia o `data-schemas.md` para confirmar os valores válidos de `fulfillment_type` (ex: `"delivery"`, `"pickup"`, `"local"`) e verificar se há labels de exibição correspondentes.

### Arquivos a modificar

- `framework/shopman/web/views/kds.py` — substituir leituras de `delivery_method` pelo helper.
- `framework/shopman/web/views/pedidos.py` — substituir fallback inline pelo helper (se Opção A).
- `framework/shopman/services/order_helpers.py` (ou equivalente) — novo helper `get_fulfillment_type` (se Opção A).

### Critério de conclusão

- [ ] `kds.py` não lê `"delivery_method"` diretamente sem fallback para `"fulfillment_type"`.
- [ ] Lógica de fallback em um único lugar (se Opção A).
- [ ] `make test` verde.

---

## WP-DS-5 — `data-schemas.md` — documentar chaves ausentes e corrigir `intent_id`

**Gravidade:** alta (governança). Chaves em uso no código não documentadas geram drift cumulativo.

### Diagnóstico

As seguintes chaves estão ausentes ou incorretas em `docs/reference/data-schemas.md`:

**Ausentes:**

1. `order.data["hold_ids"]` — escrita por `services/stock.py:48`, lida por `stock.fulfill`/`stock.release`. Registra os IDs dos holds adotados no commit.

2. `order.data["loyalty"]` — escrita pelo `LoyaltyRedeemModifier` (`modifiers.py:488`), lida por `services/loyalty.py:30`. Contém sub-chave `redeem_points_q`.

3. `session.data["delivery_address_id"]` — escrita por `web/views/checkout.py:435` (FK para `CustomerAddress`), lida por `checkout_defaults.py:125`. Não propagada ao `order.data` (uso somente em `session.data`).

**Incorretos (pós-DF-1):**

4. `data-schemas.md:143,161,332,339,371` — ainda usa `intent_id` em exemplos JSON e tabelas de payload para `order.data.payment` e eventos `pix.timeout`/`payment.capture`/`card.create`. O código de produção (`services/payment.py`) já usa `intent_ref` (corrigido em DF-1). A documentação está desatualizada.

### Solução

Ler o arquivo `docs/reference/data-schemas.md` completo para entender o formato e localização correta de cada seção. Depois:

1. Adicionar `hold_ids` na seção `Order.data`, com:
   - Tipo: `list[str]`
   - Escrito por: `StockService.hold(order)`
   - Lido por: `StockService.fulfill(order)`, `StockService.release(order)`
   - Descrição: IDs dos holds do Stockman adotados no momento do commit.

2. Adicionar `loyalty` na seção `Order.data` (e `Session.data` se também escrita na sessão), com:
   - Tipo: `dict` com sub-chave `redeem_points_q: int`
   - Escrito por: `LoyaltyRedeemModifier`
   - Lido por: `services/loyalty.py`
   - Descrição: dados de resgate de pontos de fidelidade aplicados ao pedido.

3. Adicionar `delivery_address_id` na seção `Session.data`, com:
   - Tipo: `int` (FK para `CustomerAddress.pk`)
   - Escrito por: `web/views/checkout.py`
   - Lido por: `checkout_defaults.py`
   - Nota: não propagada ao `Order.data`; usada apenas para inferência de defaults na sessão.

4. Substituir todas as ocorrências de `intent_id` por `intent_ref` nas seções de `Order.data.payment`, `pix.timeout` payload, `payment.capture` payload, e `card.create` payload. Verificar também exemplos JSON inline.

### Arquivos a modificar

- `docs/reference/data-schemas.md` — apenas documentação, sem código.

### Critério de conclusão

- [ ] `hold_ids` documentado em `Order.data`.
- [ ] `loyalty` documentado em `Order.data` (e `Session.data` se aplicável).
- [ ] `delivery_address_id` documentado em `Session.data` com nota de não-propagação.
- [ ] `grep -rn 'intent_id' docs/reference/data-schemas.md` retorna zero.
- [ ] Exemplos JSON e tabelas de payload consistentes com `intent_ref`.

---

## WP-DS-6 — Completar AF-4: `ChannelConfig.effective()` no CommitService

**Gravidade:** médio. CommitService lê `channel.config` diretamente, não herdando cascade canal←loja←defaults.

### Diagnóstico

AF-4 estava "parcialmente corrigido": `commit.py:202` agora lê a sub-chave correta:
```python
(channel.config or {}).get("rules", {}).get("checks", [])
```
Mas **não usa `ChannelConfig.effective(channel)`**. O cascade de defaults (loja → canal) é ignorado. Se a loja define `rules.checks = [...]` e o canal não sobrescreve, o CommitService não herda.

Ler `framework/shopman/config.py` para entender o método `effective(channel)` e o cascade via `deep_merge`.

### Solução

No `CommitService._do_commit()` (ou onde `rules.checks` é lido), substituir leitura direta por:
```python
from shopman.config import ChannelConfig

cfg = ChannelConfig.effective(channel)
checks = cfg.rules.checks  # herda cascade corretamente
```

Verificar outros pontos em `commit.py` que acessem `channel.config` diretamente com sub-chaves semânticas (não operacionais como `"web_adapter"`). Todos devem usar `ChannelConfig.effective()`.

Verificar também `framework/shopman/services/` e `framework/shopman/handlers/` para qualquer acesso a `channel.config.get(...)` com chaves semânticas.

### Arquivos a modificar

- `packages/orderman/shopman/orderman/services/commit.py` — usar `ChannelConfig.effective(channel)`.
- Outros call sites identificados na auditoria.

### Critério de conclusão

- [ ] `CommitService` não faz `channel.config.get("rules", {}).get(...)` diretamente.
- [ ] Usa `ChannelConfig.effective(channel).rules.checks`.
- [ ] Cascade de defaults funciona: shop com `rules.checks` configurado e canal sem override → CommitService herda os checks da loja.
- [ ] `make test` verde.

---

## WP-DS-7 — Consistência: topics + `session_key` + personas antigas

**Gravidade:** médio. Nomenclatura inconsistente gera confusão e drift cumulativo.

### Diagnóstico

Quatro grupos de inconsistências:

**Grupo 1 — `cart_key` vs `session_key`:**
O usuário confirmou: **`session_key` é o canônico**. Buscar `cart_key` no codebase:
```
grep -rn 'cart_key' framework/ packages/ --include="*.py" --include="*.html"
```
Cada ocorrência é drift. Substituir por `session_key`.

**Grupo 2 — Nomes antigos de persona em comentários/docstrings:**
- `seed.py` linhas 23,41,51,66,271,275,285,316,688,787,1220,1282,1540,1575: comentários de seção com `Offering`, `Stocking`, `Crafting`, `Ordering`.
- `modifiers.py:4`: docstring `"Modifiers follow the Ordering Modifier protocol"`.
- `middleware.py:18`: docstring `"Ordering.Session.data"`.
- `orderman/__init__.py`, `orderman/registry.py`, `orderman/context_processors.py`, `orderman/exceptions.py`: verificar e corrigir.
- `suggest_production.py:79`: referência a `Crafting`.
- Glossário (`docs/reference/glossary.md:7,18,40,48`): seções `Offering`, `Stocking`, `Crafting`, `Ordering` → `Offerman`, `Stockman`, `Craftsman`, `Orderman`.

Substituições:
- `Offering` → `Offerman`
- `Stocking` → `Stockman`
- `Crafting` → `Craftsman`
- `Ordering` → `Orderman`

**Grupo 3 — `DEFAULT_DDD` alias de backward compat:**
`framework/shopman/web/constants.py:19-20`:
```python
# Kept for backwards compat — views should prefer get_default_ddd()
DEFAULT_DDD = _DEFAULT_DDD_FALLBACK
```
Viola a convenção "zero backward-compat aliases". Verificar callers: `grep -rn 'DEFAULT_DDD' framework/`. Se nenhum caller usa `DEFAULT_DDD` diretamente, remover. Se há callers, refatorar para `get_default_ddd()` e então remover o alias.

**Grupo 4 — `Recipe.code` e `WorkOrder.code`:**
`packages/craftsman/shopman/craftsman/models/recipe.py:29` e `work_order.py:39` usam `code` em vez de `ref`. O glossário os menciona com `code`, mas a convenção geral é `ref`. Decisão a tomar: se foi deliberado, documentar explicitamente como exceção em `CLAUDE.md` na seção de convenções. Se não foi deliberado, renomear para `ref` com migração. **Consulte ADRs ou histórico antes de decidir.**

### Arquivos a modificar

- `framework/shopman/web/views/checkout.py`, `cart.py`, e demais arquivos com `cart_key` → `session_key`.
- `framework/shopman/management/commands/seed.py` — comentários de seção.
- `framework/shopman/modifiers.py:4` — docstring.
- `framework/shopman/middleware.py:18` — docstring.
- `packages/orderman/shopman/orderman/__init__.py`, `registry.py`, `context_processors.py`, `exceptions.py` — varredura e correção.
- `framework/shopman/management/commands/suggest_production.py:79`.
- `docs/reference/glossary.md` — seções renomeadas.
- `framework/shopman/web/constants.py` — remover `DEFAULT_DDD` (se sem callers).
- `CLAUDE.md` — documentar exceção de `Recipe.code`/`WorkOrder.code` (se decisão deliberada).

### Critério de conclusão

- [ ] `grep -rn 'cart_key' framework/ packages/` retorna zero.
- [ ] `grep -rn '\bOrdering\b\|\bOffering\b\|\bStocking\b\|\bCrafting\b' framework/ packages/ --include="*.py"` retorna zero em comentários/docstrings (não em imports ou namespaces).
- [ ] Glossário com seções renomeadas para personas canônicas.
- [ ] `DEFAULT_DDD` removido (ou callers migrados + removido).
- [ ] `Recipe.code`/`WorkOrder.code` com decisão documentada (exceção em CLAUDE.md ou renomeado para `ref`).
- [ ] `make test` verde.

---

## WP-DS-8 — Feature: label configurável para `handle_type`/`handle_ref` via Admin

**Gravidade:** feature. Design intencional — `handle_type`/`handle_ref` é intencionalmente genérico para flexibilidade. O gap é a ausência de um label configurável por canal que permita que a UI use o termo correto para o negócio (ex: "Comanda", "Mesa", "CPF").

### Contexto

`handle_type` e `handle_ref` em `Session` e `Order` são identificadores genéricos do cliente/sessão. Para um restaurante, pode ser "Comanda" ou "Mesa". Para um e-commerce, pode ser "CPF" ou "E-mail". A abstração é correta — o label de exibição é o que varia por negócio.

Atualmente, a UI do storefront e do KDS usa um label fixo (verificar qual). O label deveria vir de uma configuração por canal.

### Solução

Ler `framework/shopman/config.py` para entender a estrutura do `ChannelConfig`. Adicionar um campo ao sub-dataclass mais adequado (possivelmente `ChannelConfig` raiz ou nova sub-classe `UX`):

```python
@dataclass
class ChannelConfig:
    ...
    handle_label: str = "Identificador"   # ex: "Comanda", "Mesa", "CPF", "E-mail"
    handle_placeholder: str = ""           # ex: "Ex: 42", "Ex: mesa 3"
```

Ou, se preferir agrupar conceitos de UX:
```python
@dataclass
class UXConfig:
    handle_label: str = "Identificador"
    handle_placeholder: str = ""

@dataclass
class ChannelConfig:
    ...
    ux: UXConfig = field(default_factory=UXConfig)
```

Depois:
1. Expor `handle_label`/`handle_placeholder` no admin de Channel (campo de texto em JSON config ou campos dedicados na seção de configuração de UX).
2. Disponibilizar o label via context processor ou tag de template para as views do storefront, KDS e POS usarem.
3. Substituir labels hardcoded nos templates relevantes.

Verificar onde `handle_type`/`handle_ref` são exibidos:
```
grep -rn 'handle_type\|handle_ref\|handle_label' framework/shopman/web/templates/ --include="*.html"
grep -rn 'handle_type\|handle_ref' framework/shopman/web/views/ framework/shopman/admin/ --include="*.py"
```

### Arquivos a modificar

- `framework/shopman/config.py` — adicionar `handle_label`/`handle_placeholder` ao `ChannelConfig`.
- `framework/shopman/context_processors.py` — expor `handle_label` via `shop()` context.
- Templates relevantes (checkout, KDS, POS, pedidos) — usar `{{ shop.handle_label }}` em vez de label fixo.
- Admin de Channel — expor os novos campos.
- `framework/shopman/management/commands/seed.py` — configurar `handle_label` nos canais seed.
- `docs/reference/data-schemas.md` — documentar se há mudança na semântica de alguma chave.

### Critério de conclusão

- [ ] `ChannelConfig` tem `handle_label` com default `"Identificador"`.
- [ ] Admin de Channel exibe campo para `handle_label`.
- [ ] Templates do storefront/KDS/POS usam o label do config, não string hardcoded.
- [ ] Seed de Nelson configura `handle_label` apropriado (ex: "Comanda").
- [ ] `make test` verde.

---

## WP-DS-9 — Fixes menores: `emit_event` concorrência, `DEFAULT_DDD` e offline.html

**Gravidade:** baixo. Sem impacto imediato em runtime para a maioria dos casos, mas correto resolver.

> **Nota:** Se DS-7 já removeu `DEFAULT_DDD`, pular esse item neste WP.

### Diagnóstico e solução por item

**Item 1 — `OrderEvent.seq` sem `select_for_update`:**

`packages/orderman/shopman/orderman/models/order.py:254-257`:
```python
last_seq = self.events.aggregate(
    m=Coalesce(Max("seq"), Value(-1))
)["m"]
return OrderEvent.objects.create(order=self, seq=last_seq + 1, ...)
```
Dois threads concorrentes podem calcular o mesmo `last_seq` e tentar criar dois `OrderEvent` com o mesmo `seq`, violando `UniqueConstraint(fields=["order", "seq"])` → `IntegrityError` em produção sob carga.

**Opção A (preferida):** Usar `select_for_update()` no queryset de eventos antes do `aggregate`:
```python
with transaction.atomic():
    last_seq = self.events.select_for_update().aggregate(
        m=Coalesce(Max("seq"), Value(-1))
    )["m"]
    return OrderEvent.objects.create(order=self, seq=last_seq + 1, ...)
```
Isso garante lock exclusivo no nível da transação.

**Opção B:** Alterar `seq` para usar `auto_increment` do banco via `AutoField` ou `F()` expression, eliminando o cálculo manual. Mais complexo, mas elimina a classe de bug.

Implementar Opção A. Verificar se `transition_status()` já usa `select_for_update()` (mencionado no audit como correto) e seguir o mesmo padrão.

**Item 2 — `offline.html` com `onclick=`:**

`framework/shopman/templates/storefront/offline.html:65`:
```html
<button class="retry-btn" onclick="window.location.reload()">Tentar novamente</button>
```
Este é o único template servido sem Alpine.js (PWA offline). A convenção proíbe `onclick=`, mas Alpine não está disponível nesse contexto. Adicionar comentário explícito justificando a exceção:
```html
<!-- PWA offline: Alpine.js não disponível neste contexto -->
<button class="retry-btn" onclick="window.location.reload()">Tentar novamente</button>
```
Alternativa: converter para `<a href="javascript:location.reload()">` ou manter com comentário. O comentário é suficiente e pragmaticamente correto.

### Arquivos a modificar

- `packages/orderman/shopman/orderman/models/order.py` — adicionar `select_for_update()` em `emit_event()`.
- `framework/shopman/templates/storefront/offline.html` — adicionar comentário de exceção.

### Critério de conclusão

- [ ] `emit_event()` envolve cálculo de `last_seq` em `transaction.atomic()` com `select_for_update()`.
- [ ] `offline.html` tem comentário explicando exceção de Alpine.js.
- [ ] `make test` verde.

---

## Ordem de execução e dependências

| WP | Depende de | Pode rodar em paralelo com |
|---|---|---|
| DS-1 | — | DS-2, DS-3, DS-4 |
| DS-2 | — | DS-1, DS-3, DS-4 |
| DS-3 | — | DS-1, DS-2, DS-4 |
| DS-4 | — | DS-1, DS-2, DS-3 |
| DS-5 | DS-2 (para alinhar `order_id` → `order_ref` na doc) | DS-3, DS-4 |
| DS-6 | — | DS-1..DS-5 |
| DS-7 | — | DS-1..DS-6 |
| DS-8 | DS-6 (para ter `ChannelConfig` estável) | DS-7 |
| DS-9 | — | DS-1..DS-8 |

## Princípios de execução

- **Zero resíduos** (`feedback_zero_residuals`): Nenhum alias, nenhum comentário `# formerly X`.
- **Zero gambiarras** (`feedback_zero_gambiarras`): Soluções corretas. Se o fix correto exige migração, fazer migração.
- **Respeitar o core** (`feedback_respect_core_no_reinvent`): Não alterar packages sem compreender como já resolvem.
- **Sem features inventadas** (`feedback_no_invented_features`): Cada WP resolve apenas os achados documentados.
