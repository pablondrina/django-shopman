# Drift Scan — 2026-04-09

## Resumo executivo

**17 achados:** 3 críticos, 5 altos, 5 médios, 4 baixos.

Distribuição por dimensão:
- Nomenclatura (2)
- Separação framework/instância (1)
- Contratos de camadas (4)
- Dead code / código órfão (3)
- Frontend (1)
- Concorrência (1)
- Mocks em produção (1)
- Semântica e consistência (4)

---

## Achados já conhecidos (AUDIT-FIX-PLAN / DRIFT-FIX-PLAN)

### AF-1: items em notificação lidos de order.data
**Status: CORRIGIDO.**
`notification.py:191` lê `order.snapshot.get("items", [])` — confirmado na leitura atual.

### AF-2: Order.get_transitions() usando chave `order_flow`
**Status: CORRIGIDO.**
`order.py:136` lê `(self.channel.config or {}).get("flow", {}).get("transitions")` — usa a chave correta `"flow"`. Sem referência a `order_flow`.

### AF-3: Pipeline órfão + vocabulário de pagamento
**Status: CORRIGIDO.**
`config.py` não contém mais `Pipeline`. Webhooks usam `on_paid` como chave canônica. Confirmado em `webhooks/efi.py:146` e `webhooks/stripe.py:120`.

### AF-4: CommitService com `required_checks_on_commit`
**Status: PARCIALMENTE CORRIGIDO.**
`commit.py:202` agora lê `(channel.config or {}).get("rules", {}).get("checks", [])` — usa a sub-chave correta. Porém não usa `ChannelConfig.effective(channel)` e, portanto, não herda o cascade canal←loja←defaults. A correção foi em campo, não via ChannelConfig. Funciona, mas não aproveita o cascade.

### AF-5: Lógica `balcao` em services/customer.py
**Status: CORRIGIDO.**
`services/customer.py` implementa o registry pattern conforme planejado. Nenhuma referência a `_handle_balcao` ou discriminação por `channel_ref == "balcao"`.

### AF-6: `CHANNEL_REF = "web"` hardcoded em cart.py
**Status: CORRIGIDO.**
`web/cart.py:13` importa de `shopman.web.constants.STOREFRONT_CHANNEL_REF`. `web/constants.py:42` lê de settings com default `"web"`.

### AF-7: Docstrings com nomes antigos
**Status: PARCIALMENTE CORRIGIDO.** Ver achados novos abaixo (AF-7-RESIDUAL).

### DF-1: Contrato adapter de pagamento incompatível
**Status: CORRIGIDO.**
`services/payment.py` usa DTOs tipados, consome por atributo. `payment_types.py` existe com `PaymentIntent`/`PaymentResult`.

### DF-2: `_channel_config` helper em flows.py
**Status: CORRIGIDO.**
`flows.py` não contém mais `_channel_config`. Usa `_effective_config(order)` que chama `ChannelConfig.effective(order.channel)`.

### DF-3: Adoção de holds por SKU em vez de quantidade
**Status: CORRIGIDO.**
`services/stock.py` implementa `_adopt_holds_for_qty` e `_load_session_holds` conforme planejado. `_pop_matching_hold` não existe mais.

---

## Novos achados — estruturais e de runtime

### [CRÍTICO] Mismatch de tópicos fiscal: serviço emite topic inexistente

**Dimensão:** Contratos de camadas / Dead code
**Arquivo:** `framework/shopman/services/fiscal.py:34,62`
**Problema:** `fiscal.emit(order)` cria Directive com `topic="fiscal.emit"` e `fiscal.cancel(order)` com `topic="fiscal.cancel"`. Os handlers registrados escutam `"fiscal.emit_nfce"` e `"fiscal.cancel_nfce"` (constantes `FISCAL_EMIT_NFCE` / `FISCAL_CANCEL_NFCE` em `topics.py`). Nenhuma Directive criada pelo serviço fiscal será processada — todas ficam na fila como `queued` para sempre.

**Evidência:**
```python
# services/fiscal.py:34
directives.queue("fiscal.emit", order, ...)

# handlers/fiscal.py:21
topic = FISCAL_EMIT_NFCE  # = "fiscal.emit_nfce"
```

**Correção sugerida:** Substituir `"fiscal.emit"` → `FISCAL_EMIT_NFCE` e `"fiscal.cancel"` → `FISCAL_CANCEL_NFCE` em `services/fiscal.py`. Ou usar as constantes de `topics.py` importadas.

---

### [CRÍTICO] Mock de backend fiscal/accounting carregado em produção

**Dimensão:** Mocks em produção
**Arquivo:** `framework/shopman/setup.py:248-268`
**Problema:** `_load_fiscal_backend()` e `_load_accounting_backend()` — quando `SHOPMAN_FISCAL_BACKEND` não está configurado — importam e instanciam `MockFiscalBackend` e `MockAccountingBackend` de `shopman.tests._mocks`. Mocks de test são carregados no processo de produção se `SHOPMAN_FISCAL_BACKEND` não for configurado. Um typo ou ausência de configuração no deploy silenciosamente ativa mocks.

**Evidência:**
```python
# setup.py:248-252
if not backend_path:
    try:
        from shopman.tests._mocks.fiscal_mock import MockFiscalBackend
        return MockFiscalBackend()
    except ImportError:
        return None
```

**Correção sugerida:** Quando backend não configurado, retornar `None` imediatamente (como já faz quando o import falha). Mock deve ser opt-in via `SHOPMAN_FISCAL_BACKEND = "shopman.tests._mocks.fiscal_mock.MockFiscalBackend"` em settings de desenvolvimento.

---

### [CRÍTICO] `order_id` na resposta do CommitService expõe PK interna

**Dimensão:** Contratos de camadas / Semântica
**Arquivo:** `packages/omniman/shopman/omniman/services/commit.py:388-394`, `framework/shopman/api/serializers.py:45`, `framework/shopman/api/views.py:219`
**Problema:** `CommitService._do_commit()` retorna `"order_id": order.pk` (PK interna do banco) além de `"order_ref"`. O serializer da API expõe `order_id` como `IntegerField`. PKs internas não devem ser expostas via API pública — são sequenciais e revelam volume de pedidos. A convenção do projeto é usar `ref`.

**Evidência:**
```python
# commit.py:388
return {
    "order_ref": order.ref,
    "order_id": order.pk,  # ← PK interna exposta
    ...
}
# api/serializers.py:45
order_id = serializers.IntegerField()
```

**Correção sugerida:** Remover `"order_id"` da resposta do CommitService e do serializer. Caller que precise do PK deve obtê-lo via `Order.objects.get(ref=order_ref).pk` se realmente necessário.

---

### [ALTO] Canal `Channel.config` aceita chave `"pipeline"` que não existe no ChannelConfig

**Dimensão:** Contratos de camadas
**Arquivo:** `packages/omniman/shopman/omniman/models/channel.py:11`, `packages/omniman/shopman/omniman/admin.py:250-256`
**Problema:** `KNOWN_CONFIG_KEYS` em `channel.py` inclui `"pipeline"`. O admin do omniman lê `c.get("pipeline", {})` e exibe `on_commit`/`on_confirmed` dela. Mas `ChannelConfig` não tem mais `Pipeline` — foi removida no AF-3. Dois problemas: (1) `channel.clean()` não vai rejeitar configs com `"pipeline"`, e (2) o admin exibe dados de uma chave legada. Qualquer operador que configure `pipeline.on_commit` seguindo a UI do admin não terá efeito.

**Evidência:**
```python
# channel.py:11 — KNOWN_CONFIG_KEYS ainda contém "pipeline"
KNOWN_CONFIG_KEYS = frozenset({"confirmation", "payment", "stock", "pipeline", "notifications", "rules", "flow"})

# admin.py:250-255 — lê pipeline do config dict bruto
pipeline = c.get("pipeline", {})
on_commit = pipeline.get("on_commit", [])
```

**Correção sugerida:** Remover `"pipeline"` de `KNOWN_CONFIG_KEYS` em `channel.py`. Atualizar `admin.py` para remover a exibição da seção pipeline (ou redirecionar para onde `on_commit`/`on_confirmed` são realmente configurados hoje — no `ChannelConfig.Flow.auto_transitions`). O docstring de `Channel` que lista `"pipeline"` também deve ser atualizado.

---

### [ALTO] `order.data["loyalty"]` e `order.data["hold_ids"]` não documentados em data-schemas.md

**Dimensão:** Contratos de camadas
**Arquivo:** `framework/shopman/services/loyalty.py:30`, `framework/shopman/services/stock.py:48`, `docs/reference/data-schemas.md`
**Problema:** `services/loyalty.py:30` lê `order.data["loyalty"]["redeem_points_q"]`. `services/stock.py:48` escreve e lê `order.data["hold_ids"]`. Ambas as chaves estão ausentes de `data-schemas.md`. A governança do projeto exige que toda nova chave seja documentada antes de uso.

**Arquivos afetados:**
- `framework/shopman/services/loyalty.py:30`
- `framework/shopman/services/stock.py:48,111`
- `framework/shopman/modifiers.py:488` (lê `session.data["loyalty"]`)
- `docs/reference/data-schemas.md` — ambas as chaves ausentes

**Correção sugerida:** Documentar `hold_ids` (escrito por `stock.hold`, lido por `stock.fulfill`/`stock.release`) e `loyalty` (escrito pelo `LoyaltyRedeemModifier`, lido por `services/loyalty.py`) em `data-schemas.md`.

---

### [ALTO] `delivery_address_id` não documentado em data-schemas.md

**Dimensão:** Contratos de camadas
**Arquivo:** `framework/shopman/services/checkout_defaults.py:20,30,125`, `framework/shopman/web/views/checkout.py:435`
**Problema:** A chave `delivery_address_id` é escrita em `session.data` pela view de checkout (FK para `CustomerAddress`), lida por `checkout_defaults.py` para inferir preferências, mas está completamente ausente de `docs/reference/data-schemas.md`. Também não está na lista de chaves propagadas pelo `CommitService` — ou seja, não chega a `order.data`.

**Evidência:**
```python
# checkout.py:435
defaults_data["delivery_address_id"] = int(saved_address_id)
# checkout_defaults.py:125
if addr_id := data.get("delivery_address_id"):
```

**Correção sugerida:** Documentar em `data-schemas.md` como chave de `Session.data`. Avaliar se deve ser propagada ao `Order.data` ou se uso somente em `Session.data` (inferência de defaults) está correto.

---

### [ALTO] `kds.py` e `pedidos.py` leem `order.data["delivery_method"]` sem fallback semântico claro

**Dimensão:** Semântica e consistência
**Arquivo:** `framework/shopman/web/views/kds.py:42,118`, `framework/shopman/web/views/pedidos.py:63,123`
**Problema:** `pedidos.py:63` faz `order.data.get("fulfillment_type") or order.data.get("delivery_method", "")` — dois nomes para o mesmo conceito, com fallback. `kds.py:42,118` só lê `delivery_method` sem fallback para `fulfillment_type`. O `data-schemas.md` documenta `delivery_method` como chave legada "não escrita pelo checkout padrão" e `fulfillment_type` como a chave canônica. Views que só leem `delivery_method` silenciosamente recebem string vazia para pedidos do storefront (que usam `fulfillment_type`).

**Evidência:**
```python
# kds.py:42 — sem fallback para fulfillment_type
delivery_method = order.data.get("delivery_method", "")
# pedidos.py:63 — fallback correto
ft = order.data.get("fulfillment_type") or order.data.get("delivery_method", "")
```

**Correção sugerida:** Unificar todas as views para usar o padrão de `pedidos.py` como fallback. Ou, melhor, criar um helper `get_fulfillment_type(order)` centralizado.

---

## Novos achados — semântica e consistência

### [MÉDIO] Glossário usa nomes antigos de subdomínio

**Dimensão:** Nomenclatura / Semântica
**Arquivo:** `docs/reference/glossary.md:7,18,40,48`
**Problema:** O glossário usa as seções `## Offering (Catálogo)`, `## Stocking (Estoque)`, `## Crafting (Produção)`, `## Ordering (Pedidos)`. A convenção ativa é `Offerman`, `Stockman`, `Craftsman`, `Omniman`. Os nomes antigos no glossário são vetores de confusão para agentes futuros.

**Correção sugerida:** Renomear as seções do glossário para `## Offerman (Catálogo)`, `## Stockman (Estoque)`, `## Craftsman (Produção)`, `## Omniman (Pedidos)`.

---

### [MÉDIO] `Recipe.code` e `WorkOrder.code` usam `code` em vez de `ref`

**Dimensão:** Nomenclatura
**Arquivo:** `packages/craftsman/shopman/craftsman/models/recipe.py:29`, `packages/craftsman/shopman/craftsman/models/work_order.py:39`
**Problema:** Ambos os modelos têm campo `code` como identificador textual único (`SlugField`/`CharField`). A convenção do projeto é `ref` para identificadores textuais. O glossário documenta `Recipe` com `code único`. Dois vetores conflitantes: a regra geral diz `ref`, o glossário documenta `code` como canônico para Recipe.

**Evidência:**
```python
# recipe.py:29
code = models.SlugField(unique=True, ...)
# work_order.py:39
code = models.CharField(unique=True, ...)
```

**Canônico sugerido:** Avaliar se `code` foi uma decisão deliberada para Recipe/WorkOrder (glossário os menciona explicitamente com `code`). Se deliberada, documentar a exceção em CLAUDE.md. Se não, renomear para `ref` com migração.

---

### [MÉDIO] Constante `DEFAULT_DDD` com comentário "backwards compat"

**Dimensão:** Nomenclatura / Convenções
**Arquivo:** `framework/shopman/web/constants.py:19-20`
**Problema:** A convenção é zero backward-compat aliases. `constants.py` tem `DEFAULT_DDD = _DEFAULT_DDD_FALLBACK` com comentário "Kept for backwards compat — views should prefer get_default_ddd()". Isso é exatamente o tipo de alias proibido pelas convenções do projeto.

**Evidência:**
```python
# constants.py:19-20
# Kept for backwards compat — views should prefer get_default_ddd()
DEFAULT_DDD = _DEFAULT_DDD_FALLBACK
```

**Correção sugerida:** Verificar se `DEFAULT_DDD` ainda é referenciado em algum lugar. Se não, remover. Se sim, refatorar os callers para `get_default_ddd()` e então remover.

---

### [MÉDIO] `ChannelConfig` expõe "pipeline" no docstring do `Channel.config` help_text

**Dimensão:** Nomenclatura / Semântica
**Arquivo:** `packages/omniman/shopman/omniman/models/channel.py:22-23,70`
**Problema:** O docstring da classe `Channel` e o `help_text` do campo `config` ainda listam `pipeline` como um dos 7 aspectos do ChannelConfig. `ChannelConfig` não tem mais `Pipeline`. A documentação inline contradiz a implementação real.

**Evidência:**
```python
# channel.py:22-23
Config segue o schema do ChannelConfig dataclass (7 aspectos):
confirmation, payment, stock, pipeline, notifications, rules, flow.
# channel.py:70
"pipeline {on_commit, on_confirmed, on_cancelled, ...} (listas de topics), "
```

**Correção sugerida:** Atualizar docstring e help_text para refletir os 6 aspectos reais: `confirmation, payment, stock, notifications, rules, flow`.

---

### [BAIXO] Nomes antigos de subdomínio em comentários do seed.py

**Dimensão:** Nomenclatura (residual AF-7)
**Arquivo:** `framework/shopman/management/commands/seed.py:23,41,51,66,271,275,285,316,688,787,1220,1282,1540,1575`
**Problema:** O `seed.py` usa extensivamente `# Offering (catalogo)`, `# Stocking (estoque)`, `# Crafting (producao)`, `# Ordering` em comentários de seção. AF-7 estava pendente de limpeza desses comentários.

**Correção sugerida:** Substituir nos comentários: `Offering` → `Offerman`, `Stocking` → `Stockman`, `Crafting` → `Craftsman`, `Ordering` → `Omniman`.

---

### [BAIXO] `modifiers.py` docstring refere "Ordering Modifier protocol"

**Dimensão:** Nomenclatura (residual AF-7)
**Arquivo:** `framework/shopman/modifiers.py:4`
**Problema:** `modifiers.py` linha 4 diz "Modifiers follow the Ordering Modifier protocol". Deveria dizer "Omniman Modifier protocol".

**Correção sugerida:** Substituir `Ordering` → `Omniman` no docstring.

---

### [BAIXO] `middleware.py` refere "Ordering.Session" no docstring

**Dimensão:** Nomenclatura (residual AF-7)
**Arquivo:** `framework/shopman/middleware.py:18`
**Problema:** `middleware.py:18` diz "This is later propagated to Ordering.Session.data". Deveria ser "Omniman.Session.data".

**Correção sugerida:** Substituir `Ordering.Session` → `Omniman.Session`.

---

### [BAIXO] onclick em template offline.html viola convenção Alpine.js

**Dimensão:** Frontend
**Arquivo:** `framework/shopman/templates/storefront/offline.html:65`
**Problema:** `<button class="retry-btn" onclick="window.location.reload()">`. A convenção proíbe `onclick=`. Exceção para `window.location.reload()` é razoável por ser funcionalidade de browser sem equivalente Alpine de uso comum, mas o template offline é o único arquivo servido sem Alpine carregado (PWA offline), então Alpine não estaria disponível de qualquer forma. Tecnicamente correto, mas viola a regra textual.

**Evidência:**
```html
<button class="retry-btn" onclick="window.location.reload()">Tentar novamente</button>
```

**Correção sugerida:** Documentar como exceção explícita no comentário, ou converter para `<button onclick="window.location.reload()">` com comentário `<!-- PWA offline: Alpine não disponível -->`.

---

### [BAIXO] `OrderEvent.seq` calculado com `aggregate(Max)` sem `select_for_update`

**Dimensão:** Concorrência
**Arquivo:** `packages/omniman/shopman/omniman/models/order.py:254-257`
**Problema:** `Order.emit_event()` calcula `last_seq = self.events.aggregate(Max("seq"))["m"]` e então cria `OrderEvent` com `seq = last_seq + 1`. Sem `select_for_update` no cálculo do MAX, dois threads concorrentes podem calcular o mesmo `last_seq` e violar a `UniqueConstraint(fields=["order", "seq"])`. A violação lança `IntegrityError` — não é silent, mas é um runtime error possível.

O `transition_status()` correto usa `select_for_update()`, mas `emit_event()` não.

**Evidência:**
```python
# order.py:254-257
last_seq = self.events.aggregate(
    m=Coalesce(Max("seq"), Value(-1))
)["m"]
return OrderEvent.objects.create(order=self, seq=last_seq + 1, ...)
```

**Correção sugerida:** Adicionar lock de transação em `emit_event` ou usar `get_or_create` com retry, ou alterar a estratégia de seq para ser baseada em `auto_increment` do banco (não calculado).

---

## Achado adicional — KNOWN_CONFIG_KEYS vs ChannelConfig real

### [MÉDIO] `KNOWN_CONFIG_KEYS` em channel.py inclui chave `"pipeline"` removida

Já detalhado acima na seção de achados estruturais. Resumo: o conjunto de validação no `clean()` aceita `"pipeline"` como chave válida, mas `ChannelConfig` não tem mais esse aspecto. Configs de canal com `"pipeline"` não geram warning de validação.

---

## Termos do glossário com drift

| Termo canônico | Sinônimos encontrados | Arquivos | Impacto |
|---|---|---|---|
| `Omniman` | `Ordering` | `omniman/__init__.py`, `omniman/registry.py`, `omniman/context_processors.py`, `omniman/exceptions.py`, `seed.py`, `modifiers.py`, `middleware.py`, `web/cart.py` | Baixo — comentários e docstrings, não código executável |
| `Offerman` | `Offering` | `seed.py` (comentários de seção), `omniman/admin.py` | Baixo |
| `Stockman` | `Stocking` | `seed.py` (comentários de seção) | Baixo |
| `Craftsman` | `Crafting` | `seed.py` (comentários de seção), `suggest_production.py:79` | Baixo |
| `fulfillment_type` | `delivery_method` | `kds.py:42,118`, `pedidos.py:123`, `auth.py:112` | Médio — kds.py só lê `delivery_method`, silenciosamente recebe `""` para pedidos storefront |
| `intent_ref` | `intent_id` | `data-schemas.md` (documentação do `payment` payload), `pix.timeout` payload | Médio — data-schemas.md ainda documenta `intent_id` em alguns lugares após DF-1 |

---

## Verificação de `intent_id` pós-DF-1

O plano DF-1 exigia renomear `intent_id` → `intent_ref` em todos os lugares. Verificando:

- `data-schemas.md:143` — `"intent_id": "INT-abc123"` no exemplo JSON de `Order.data.payment`
- `data-schemas.md:161` — `intent_id | string | PixGenerateHandler` na tabela payment
- `data-schemas.md:332,339` — `intent_id` nos payloads de `pix.timeout` e `payment.capture`
- `data-schemas.md:371` — `intent_id` em `card.create` write-back

O código de produção (`services/payment.py`) já usa `intent_ref`. A documentação `data-schemas.md` ainda usa `intent_id`. Esta inconsistência pode induzir agentes a escrever `intent_id` em código novo.

---

## Itens verificados sem achados

- **Separação framework/instância (AF-5):** OK — `services/customer.py` usa registry pattern. Sem referência a `_handle_balcao` ou discriminação por nome de canal Nelson.
- **`CHANNEL_REF` hardcoded (AF-6):** OK — lê de settings via `SHOPMAN_STOREFRONT_CHANNEL_REF`.
- **Webhooks pagamento (AF-3):** OK — `efi.py` e `stripe.py` usam `dispatch(order, "on_paid")` e `auto_transitions["on_paid"]`. Zero ocorrências de `on_payment_confirm`.
- **DF-2 `_channel_config`:** OK — helper removido, `flows.py` usa `_effective_config(order)`.
- **DF-3 `_pop_matching_hold`:** OK — substituído por `_adopt_holds_for_qty`.
- **Campos monetários sem `_q`:** OK — nenhum campo monetário sem sufixo `_q` em BigIntegerField/IntegerField encontrado.
- **Campos `code` incorretos:** OK nos models principais. `Recipe.code` e `WorkOrder.code` são deliberados conforme glossário (documentado acima como ambiguidade).
- **Importações de `instances/`:** OK — nenhuma encontrada no framework.
- **Leituras diretas de `channel.config[key]` semântico:** OK — apenas o `adapters/__init__.py` lê `channel.config.get("<type>_adapter")` para resolver adaptadores, o que é operacional, não semântico.
- **`order.data` vs `order.snapshot`:** OK — `notification.py` corretamente usa `order.snapshot.get("items", [])` (AF-1 corrigido).
- **Sequências sem lock em services principais:** `transition_status()` usa `select_for_update()`. `emit_event()` não — registrado acima.
- **Imports de `instances/` no framework:** OK — zero ocorrências.
- **Tópicos stock, pix, payment, card:** Topics `stock.*`, `pix.*`, `payment.*`, `card.*` não estão em `topics.py`, mas esses handlers pertencem a um subsistema diferente (omniman registry diretamente). Verificado: os handlers de stock/pix/payment/card são registrados diretamente pelo omniman core, não pelo framework. OK.
