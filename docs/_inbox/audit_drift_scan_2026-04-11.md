# Drift Scan — 2026-04-11

## Resumo executivo

**13 achados:** 2 críticos, 5 altos, 3 médios, 3 baixos.  
Distribuição: Nomenclatura(2), Separação(3), Contratos(3), Dead code(1), Frontend(0), Concorrência(0), Mocks(0), Vocabulário(1), Semântica(1), Regressão(2).

---

## Achados já conhecidos (AUDIT-FIX-PLAN) — status atualizado

| WP | Status | Observação |
|----|--------|------------|
| AF-1 `notification.py` lê items de `order.data` | ✅ CORRIGIDO | `_build_context` agora lê `order.snapshot.get("items", [])` |
| AF-2 `get_transitions()` via ChannelConfig | ⚠️ PARCIAL | Implementado via `snapshot["lifecycle"]`, mas `lifecycle` nunca é populado — ver **[CRÍTICO] AF-2** abaixo |
| AF-3 `ChannelConfig.Pipeline` + `on_payment_confirm` | ✅ CORRIGIDO | Pipeline removido, webhooks usam `on_paid` |
| AF-4 `required_checks_on_commit` → `ChannelConfig.rules.checks` | ✅ CORRIGIDO | commit.py usa `effective_config.get("rules", {}).get("checks", [])` |
| AF-5 `customer.py` discriminação por `channel_ref == "balcao"` | ✅ CORRIGIDO | Registry pattern implementado; sem `_handle_balcao` em services |
| AF-6 `STOREFRONT_CHANNEL_REF` hardcoded | ✅ CORRIGIDO | `constants.py:35` lê `getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")` |

**DRIFT-FIX-PLAN — todos corrigidos:**

| WP | Status | Evidência |
|----|--------|-----------|
| DF-1 Contrato adapters de pagamento (DTOs) | ✅ CORRIGIDO | `payment_types.py` com `PaymentIntent`/`PaymentResult`; três adapters retornam DTOs |
| DF-2 `_channel_config` helper + bypass de ChannelConfig | ✅ CORRIGIDO | `flows.py` usa `ChannelConfig.for_channel()`; zero ocorrências de `_channel_config` |
| DF-3 `_pop_matching_hold` / sangria de estoque | ✅ CORRIGIDO | `stock.py` usa `_adopt_holds_for_qty` por quantidade |

---

## Novos achados — estruturais e de runtime

### [CRÍTICO] AF-2 regrediu: `snapshot["lifecycle"]` sempre vazio

**Dimensão:** Contratos entre camadas  
**Arquivo:** `packages/orderman/shopman/orderman/services/commit.py:314` + `packages/orderman/shopman/orderman/models/order.py:146-147`  
**Problema:** A solução de AF-2 gravou `lifecycle` no snapshot para que `get_transitions()` e `get_terminal_statuses()` pudessem ler customizações per-canal. Porém, o `commit.py` obtém esse valor via `effective_config.get("lifecycle", {})`. A chave `"lifecycle"` **não existe** no schema de `ChannelConfig` — não é um campo da dataclass. `asdict(ChannelConfig.for_channel(...))` nunca produz uma chave `"lifecycle"`. Resultado: `snapshot["lifecycle"]` é sempre `{}`, `get_transitions()` sempre cai em `DEFAULT_TRANSITIONS`, e transições customizadas por canal são silenciosamente ignoradas.

**Evidência:**
```python
# commit.py:314 — chave "lifecycle" não existe em ChannelConfig.to_dict()
"lifecycle": effective_config.get("lifecycle", {}),  # sempre {}

# order.py:146-147 — nunca tem transitions
lifecycle = (self.snapshot or {}).get("lifecycle", {})
return lifecycle.get("transitions") or self.DEFAULT_TRANSITIONS  # sempre DEFAULT_TRANSITIONS
```

**Correção sugerida:** Ou (a) adicionar campo `lifecycle` ao ChannelConfig (com `transitions` e `terminal_statuses`), ou (b) remover a lógica de `snapshot["lifecycle"]` completamente se transições customizadas por canal não são necessárias.

---

### [CRÍTICO] POS bypassa ChannelConfig no commit e no modify

**Dimensão:** Contratos entre camadas  
**Arquivo:** `framework/shopman/web/views/pos.py:265-292`  
**Problema:** A view POS chama `ModifyService.modify_session()` (linha 266) e `CommitService.commit()` (linha 287) sem passar `channel_config`. Ambos os serviços recebem `channel_config=None` e fazem `effective_config = channel_config or {}` — config vazio. O canal `"balcao"` pode ter `confirmation.mode`, `payment.timing`, `rules.checks` customizados, mas eles são silenciosamente ignorados. O POS usa comportamento padrão hardcoded.

**Evidência:**
```python
# pos.py:265-292
ModifyService.modify_session(
    session_key=session_key,
    channel_ref="balcao",
    ops=ops,
    ctx={"actor": f"pos:{request.user.username}"},
    # channel_config ausente!
)
result = CommitService.commit(
    session_key=session_key,
    channel_ref="balcao",
    idempotency_key=generate_idempotency_key(),
    ctx={"actor": f"pos:{request.user.username}"},
    # channel_config ausente!
)
```

**Contraste:** `checkout.py` (storefront) resolve corretamente via `asdict(ChannelConfig.for_channel(channel))` antes de chamar `CommitService.commit()`.

**Correção sugerida:** Espelhar o padrão de `checkout.py`: resolver `config = ChannelConfig.for_channel(channel)` e passar `channel_config=asdict(config)` para ambas as chamadas.

---

### [ALTO] URL paths com forma gerúndio proibida

**Dimensão:** Nomenclatura  
**Arquivo:** `framework/project/urls.py:33-36`  
**Problema:** Quatro URL paths usam a forma gerúndio das personas — forma explicitamente proibida pelas convenções (memória `feedback_persona_names_only`). URLs são interface pública e inconsistência pode gerar confusão em documentação de API.

**Evidência:**
```python
urlpatterns += _include_optional("api/ordering/", ...)  # deve ser "api/orderman/"
urlpatterns += _include_optional("api/offering/", ...)  # deve ser "api/offerman/"
urlpatterns += _include_optional("api/stocking/", ...)  # deve ser "api/stockman/"
urlpatterns += _include_optional("api/crafting/", ...)  # deve ser "api/craftsman/"
```

**Correção sugerida:** Renomear os prefixos de URL para os nomes canônicos das personas.

---

### [ALTO] `"balcao"` hardcoded na view POS (violação framework/instância)

**Dimensão:** Separação framework/instância  
**Arquivo:** `framework/shopman/web/views/pos.py:50,77,205,268,289,334`  
**Problema:** A view POS referencia `"balcao"` diretamente em 6 lugares: query de listing, check D-1, busca de channel, chamadas de ModifyService e CommitService. AF-5 corrigiu `services/customer.py` mas a view POS permanece Nelson-específica no framework.

**Evidência:**
```python
listing__ref="balcao"         # linha 50
listing_ref="balcao"          # linha 77
Channel.objects.get(ref="balcao")  # linha 205
channel_ref="balcao",         # linhas 268, 289
# + origem hardcoded: ops.append({"op": "set_data", "path": "origin_channel", "value": "pos"})
```

**Correção sugerida:** Parametrizar via settings (`SHOPMAN_POS_CHANNEL_REF`) seguindo o padrão de `SHOPMAN_STOREFRONT_CHANNEL_REF` já implementado em AF-6.

---

### [ALTO] Payment method `"cartao"` e `"dinheiro"` não-canônicos em POS

**Dimensão:** Separação framework/instância + semântica  
**Arquivo:** `framework/shopman/web/views/pos.py:94-98`, `framework/shopman/services/payment.py:40`  
**Problema:** O POS usa strings `"dinheiro"` e `"cartao"` (português) como valores de `payment.method`. O schema canônico (ChannelConfig.Payment) define `"counter"`, `"pix"`, `"card"`, `"external"`. `"dinheiro"` tem um tratamento especial em `payment.initiate()` (linha 40), mas `"cartao"` não — se `payment.timing` não for `"external"`, `payment.initiate()` tentará buscar um adapter para `"cartao"` e falhará silenciosamente. Além disso, esses valores são gravados em `order.data["payment"]["method"]` e consultados em queries (ex: `cash_register.py:74` filtra por `data__payment__method="dinheiro"`).

**Evidência:**
```python
# pos.py:94-98
_PAYMENT_METHODS = [
    ("dinheiro", "Dinheiro"),  # não-canônico
    ("pix", "PIX"),
    ("cartao", "Cartão"),      # não-canônico — deveria ser "card"
]

# payment.py:40 — whitelist inclui "dinheiro" mas não "cartao"
if not method or method in ("counter", "external", "dinheiro"):
    return
```

**Correção sugerida:** Usar strings canônicas (`"counter"`, `"card"`) nos valores internos. Labels de display podem ser arbitrários. Ou, se `"dinheiro"` é intencional como alias de `"counter"`, documentar e adicionar `"cartao"` à whitelist de `payment.initiate()` — mas a solução correta é usar `"card"`.

---

### [ALTO] `order.data["hold_ids"]` — schema documentado incorreto

**Dimensão:** Contratos entre camadas  
**Arquivo:** `docs/reference/data-schemas.md:130` vs `framework/shopman/services/stock.py:57,77`  
**Problema:** O schema documenta `hold_ids` como `list[str]` (IDs de holds), mas o código grava e lê `list[dict]` com estrutura `[{"sku": ..., "hold_id": ..., "qty": ...}]`. A documentação descreve um contrato que não existe.

**Evidência:**
```python
# stock.py:57 — declarado como list[dict]
hold_ids: list[dict] = []

# stock.py:77 — appenda dicts
hold_ids.append({"sku": comp_sku, "hold_id": hid, "qty": float(hqty)})

# flows.py:232 — lê como list[dict]
held_skus = {h.get("sku") for h in (order.data or {}).get("hold_ids", [])}
```

**Correção sugerida:** Corrigir `data-schemas.md` para refletir o tipo real: `list[dict]` com schema `[{sku, hold_id, qty}]`.

---

### [MÉDIO] Glossário: ChannelConfig com "6 aspectos" (são 8)

**Dimensão:** Semântica / documentação  
**Arquivo:** `docs/reference/glossary.md:79`  
**Problema:** O glossário descreve ChannelConfig como tendo "6 aspectos (confirmation, payment, stock, notifications, rules, flow)". O model real tem 8 aspectos: `confirmation`, `payment`, `fulfillment`, `stock`, `notifications`, `pricing`, `editing`, `rules`. Dois aspectos (`fulfillment` e `pricing`) e o campo `editing` estão ausentes do glossário, e `flow` é mencionado mas não existe mais no schema.

**Evidência:** `framework/shopman/config.py:125-132` lista 8 campos. `glossary.md:79` lista 6.

**Correção sugerida:** Atualizar o glossário com a lista correta dos 8 aspectos.

---

### [MÉDIO] Chaves `stock_check_unavailable` e `manual_discount` não documentadas em Session.data

**Dimensão:** Contratos entre camadas  
**Arquivo:** `docs/reference/data-schemas.md` (ausência)  
**Problema:** Duas chaves são gravadas em `session.data` mas não aparecem na tabela do schema:
- `stock_check_unavailable` (bool): escrito por `checkout.py:331` quando o check de estoque falhou silenciosamente.
- `manual_discount` (dict): escrito por `pos.py:259-263` e lido por `ManualDiscountModifier`. Regra do projeto: "toda nova chave deve ser documentada aqui antes de ser usada."

**Evidência:**
```python
# checkout.py:330-331
if stock_check_unavailable:
    checkout_data["stock_check_unavailable"] = True

# pos.py:259-263
ops.append({"op": "set_data", "path": "manual_discount.type", ...})
```

**Correção sugerida:** Adicionar ambas as chaves à tabela `Session.data` em `data-schemas.md`.

---

## Novos achados — semântica e consistência

### [BAIXO] `delivery_method` — dois conceitos diferentes com o mesmo nome

**Conceito afetado:** Canal de entrega  
**Nomes encontrados:** `delivery_method` para OTP (doorman) e `delivery_method` como chave legacy de fulfillment_type (orderman)  
**Arquivos:**
- `packages/doorman/.../models/verification_code.py:122` — campo de model para canal de entrega de OTP (whatsapp/sms/email)
- `packages/orderman/.../models/order.py:211` — fallback legacy para `fulfillment_type`
- `framework/shopman/web/views/auth.py:112-114` — usa `delivery_method` como parâmetro de POST  

**Impacto:** O mesmo nome descreve conceitos semanticamente distintos em dois domínios. Baixo impacto prático (estão em packages separados) mas pode causar confusão ao ler código que mistura os contextos.

---

### [BAIXO] `customer_name` flat vs `customer.name` aninhado

**Conceito afetado:** Nome do cliente no pedido  
**Nomes encontrados:** `order.data.get("customer_name")` (flat) e `order.data.get("customer", {}).get("name")` (nested)  
**Arquivos:**
- `framework/shopman/web/views/kds.py:42,118` — lê `order.data.get("customer_name", "")`
- `framework/shopman/web/views/pedidos.py:131` — idem  
- `framework/shopman/handlers/notification.py:197-199` — lê `order.data.get("customer", {}).get("name", "")`

**Canônico:** `order.data["customer"]["name"]` (documentado em data-schemas.md como canonical). A chave flat `customer_name` está documentada como "convenience fallback" para canais que achatam o dado — mas os próprios views do framework estão usando o fallback como caminho primário.

---

## Itens verificados sem achados

- **Frontend (Passo 5):** Nenhuma violação HTMX/Alpine encontrada — zero `onclick=`, `onchange=`, `document.getElementById` em templates.
- **Concorrência (Passo 6a-6c):** `select_for_update` aplicado corretamente em sequences, holds, fulfillment, orders; `apps.py` sem bare except no startup.
- **Mocks em produção (Passo 7):** Nenhum mock importado fora de `tests/`. `payment_mock.py` está em `adapters/` (correto).
- **Handlers órfãos (Passo 4b):** Todos os handlers têm topics emitidos (`notification.send`, `fulfillment.create`, `confirmation.timeout`, etc.) — nenhum dead handler.
- **Imports de instances/ no framework (Passo 2d):** Zero ocorrências.
- **Referências Nelson hardcoded em framework/shopman/ (Passo 2a):** Zero ocorrências.
- **Personas antigas em código não-import (Passo 1c):** Hits do grep são todos `ordering` no contexto de Meta.ordering Django — não violações de persona.
- **DF-1/DF-2/DF-3 do DRIFT-FIX-PLAN:** Todos verificados como corrigidos.
- **AF-1/AF-3/AF-5/AF-6 do AUDIT-FIX-PLAN:** Todos verificados como corrigidos.

---

## Lint (produção, não-test) — destaques

Total: 238 erros lint, maioria em tests. Em produção (não-test), os mais relevantes:

| Arquivo | Erro | Detalhe |
|---------|------|---------|
| `framework/shopman/models/cash_register.py:63` | F401 | `importlib` importado sem uso |
| `framework/shopman/web/views/catalog.py:19` | F401 | `decimal.Decimal` importado sem uso |
| `framework/shopman/web/views/pos.py` | F401 | `BaseModelAdmin` de craftsman importado sem uso |
| `framework/shopman/templatetags/storefront_tags.py:128` | F841 | `session` atribuído mas não usado |
| `framework/shopman/services/fiscal.py:8` | B007 | Variável de loop `sz_name` não usada no corpo |
| `framework/shopman/management/commands/suggest_production.py:46` | B007 | `season_name` não usado no corpo do loop |
| `packages/craftsman/.../contrib/admin_unfold/__init__.py` | F401 | `BaseTabularInline`, `format_quantity`, `format_html` importados sem uso |
| `packages/doorman/.../senders.py` | F401 | `unittest.mock.patch` importado (verificar: pode ser falso-positivo) |
| `packages/guestman/.../api/views.py` | F401 | `Sum`, `BaseModelAdmin` importados sem uso |

Comando para corrigir automaticamente: `make lint --fix` (apenas fixable F401/F841).
