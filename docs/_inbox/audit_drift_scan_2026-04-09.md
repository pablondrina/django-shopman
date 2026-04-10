# Drift Scan — 2026-04-09 (rev 2)

> Revisão 2 — corrige status de achados que já foram resolvidos entre a rev 1 e agora, e acrescenta novos achados identificados no rescan.

## Resumo executivo

**10 achados ativos:** 0 críticos, 4 altos, 4 médios, 2 baixos.

Os 3 críticos da rev 1 foram resolvidos (WP-DS-1 fiscal topics, WP-DS-2 order_id, e mock de backend). Novos achados médios adicionados: `handlers/customer.py` com `balcao` hardcode (AF-5 incompleto) e `OfferingPricingBackend` (nome de persona antigo).

---

## Status das correções anteriores

### AF-1: items em notificação lidos de order.data
**Status: CORRIGIDO.** `notification.py` lê `order.snapshot.get("items", [])`.

### AF-2: Order.get_transitions() usando chave `order_flow`
**Status: CORRIGIDO.** `order.py` lê `channel.config.get("flow", {}).get("transitions")`.

### AF-3: Pipeline órfão + vocabulário de pagamento
**Status: CORRIGIDO.** `config.py` não contém mais `Pipeline`. Webhooks usam `on_paid`. Confirmado em `webhooks/efi.py` e `webhooks/stripe.py`.

### AF-4: CommitService com `required_checks_on_commit`
**Status: PARCIALMENTE CORRIGIDO.**
`commit.py` lê `channel_config.get("rules", {}).get("checks", [])` via parâmetro injetado pelo framework — usa a sub-chave correta e recebe config com cascade via `ChannelConfig.for_channel()`. O kernel não lê `channel.config` diretamente. Funcionalmente correto.

### AF-5: Lógica `balcao` em services/customer.py
**Status: PARCIALMENTE CORRIGIDO — ver achado ativo abaixo.**
`services/customer.py` foi refatorado para registry pattern. Porém `handlers/customer.py` ainda tem `elif channel_ref == "balcao"` e `_handle_balcao()`. A correção foi incompleta — dois arquivos precisavam ser atualizados.

### AF-6: `CHANNEL_REF = "web"` hardcoded em cart.py
**Status: CORRIGIDO.** Lê de settings via `SHOPMAN_STOREFRONT_CHANNEL_REF`.

### AF-7: Docstrings com nomes antigos
**Status: PARCIALMENTE CORRIGIDO.** Residuais em `seed.py`, `modifiers.py`, `middleware.py`. Ver achados ativos abaixo.

### DF-1: Contrato adapter de pagamento incompatível
**Status: CORRIGIDO.** `services/payment.py` usa DTOs tipados (`PaymentIntent`/`PaymentResult`). `data-schemas.md` usa `intent_ref` em todos os lugares.

### DF-2: `_channel_config` helper em flows.py
**Status: CORRIGIDO.** `flows.py` usa `_effective_config(order)` → `ChannelConfig.for_channel(order.channel)`.

### DF-3: Adoção de holds por SKU em vez de quantidade
**Status: CORRIGIDO.** `services/stock.py` implementa `_adopt_holds_for_qty`.

### WP-DS-1: Mismatch de tópicos fiscal
**Status: CORRIGIDO.** `services/fiscal.py` importa e usa `FISCAL_EMIT_NFCE` / `FISCAL_CANCEL_NFCE` de `shopman.directives`.

### WP-DS-2: `order_id` na resposta do CommitService expõe PK interna
**Status: CORRIGIDO.** `commit.py` retorna apenas `order_ref`, `status`, `total_q`, `items_count`. `api/serializers.py` não contém `order_id`.

### WP-DS-3: `KNOWN_CONFIG_KEYS` e `pipeline` em channel.py
**Status: CORRIGIDO.** `channel.py` não contém mais `KNOWN_CONFIG_KEYS` nem referências a `pipeline`. O modelo `Channel` está limpo.

### WP-DS-4: `kds.py` e `pedidos.py` com `delivery_method` sem fallback
**Status: CORRIGIDO.** `kds.py:15` e `pedidos.py:17` importam `get_fulfillment_type` de `services/order_helpers.py` e o usam consistentemente.

### WP-DS-5: `delivery_address_id` não documentado em data-schemas.md
**Status: PENDENTE.** Chave ainda não consta em `data-schemas.md`.

### WP-DS-6: Cascade do CommitService via ChannelConfig
**Status: CORRIGIDO (via mecanismo diferente).** O framework injeta `channel_config` como parâmetro resolvido com cascade. O kernel não lê `channel.config` diretamente.

### WP-DS-7: Consistência de nomes (persona, cart_key, DEFAULT_DDD)
**Status: PARCIALMENTE CORRIGIDO.** `cart_key` e `DEFAULT_DDD` foram corrigidos. Residuais de persona em comentários e docstrings permanecem (ver achados abaixo).

---

## Achados ativos

### [ALTO] AF-5 incompleto: `handlers/customer.py` ainda tem `balcao` hardcode

**Dimensão:** Separação framework/instância
**Arquivo:** `framework/shopman/handlers/customer.py:80,167`

`services/customer.py` foi migrado para registry pattern, mas `handlers/customer.py` não. Linha 80 ainda tem `elif channel_ref == "balcao": customer, created = self._handle_balcao(order)`. O método `_handle_balcao()` existe em linha 167. Este código nunca será invocado via registry — é dead code Nelson-específico no caminho de handlers genéricos do framework.

**Arquivos com `channel__ref="balcao"` hardcoded além do handler:**
- `framework/shopman/models/cash_register.py:69` — `Order.objects.filter(channel__ref="balcao", ...)`
- `framework/shopman/web/views/pos.py:330` — `Order.objects.filter(channel__ref="balcao", ...)`

**Correção sugerida:** Remover `_handle_balcao()` e o branch `elif channel_ref == "balcao"` de `handlers/customer.py`. Para `cash_register.py` e `pos.py`, generalizar o filtro (ex: `channel__kind="pos"`) ou ler o ref de settings.

---

### [ALTO] `OfferingPricingBackend` usa nome de persona antiga

**Dimensão:** Nomenclatura
**Arquivos:**
- `framework/shopman/handlers/pricing.py:24` — `class OfferingPricingBackend:`
- `framework/shopman/handlers/__init__.py:51` — string de caminho `"shopman.handlers.pricing.OfferingPricingBackend"`
- `framework/shopman/handlers/__init__.py:174,185` — import e instanciação

A convenção ativa é `Offerman`, não `Offering`. Esta classe deveria ser `OffermanPricingBackend`.

**Correção sugerida:** Renomear `OfferingPricingBackend` → `OffermanPricingBackend` em `pricing.py` e atualizar todas as referências em `handlers/__init__.py`.

---

### [ALTO] `OrderingOrderHistoryBackend` usa nome de persona antiga

**Dimensão:** Nomenclatura
**Arquivo:** `packages/guestman/shopman/guestman/adapters/ordering.py`

O módulo inteiro (`ordering.py`) e a classe `OrderingOrderHistoryBackend` usam "Ordering" — persona antiga para Omniman. O docstring, a configuração de exemplo, e o nome da classe todos usam a nomenclatura descontinuada.

**Correção sugerida:** Renomear para `OmnimanOrderHistoryBackend`, o módulo para `omniman.py`, e atualizar a string de configuração de exemplo no docstring.

---

### [ALTO] `pedidos.py` lê `order.data["payment"]["status"]` em vez do Payman

**Dimensão:** Contratos de camadas
**Arquivo:** `framework/shopman/web/views/pedidos.py:158`

```python
"payment_status": order.data.get("payment", {}).get("status", ""),
```

O contrato estabelecido (WP-DS-2, `services/payment.py` docstring) é que o status de pagamento vive no Payman — `order.data["payment"]` armazena apenas chaves de display (`intent_ref`, `method`, `qr_code`, etc.). Ler `status` de `order.data["payment"]` retornará sempre string vazia para pedidos novos.

**Correção sugerida:** Consultar `PaymentService.get(intent_ref).status` do Payman, ou remover o campo se não for necessário na view.

---

### [MÉDIO] Glossário usa nomes antigos de subdomínio e método inexistente

**Dimensão:** Nomenclatura / Semântica
**Arquivo:** `docs/reference/glossary.md:7,18,40,48,79`

- Seções `## Offering`, `## Stocking`, `## Crafting`, `## Ordering` — deveriam ser `## Offerman`, `## Stockman`, `## Craftsman`, `## Omniman`
- `ChannelConfig` entry (linha 79): "7 aspectos... pipeline, notifications..." — `pipeline` não existe mais; são 6 aspectos. O método é listado como `effective()` mas o método real é `for_channel()`.

**Correção sugerida:** Renomear seções e corrigir a entry de ChannelConfig para 6 aspectos com método `for_channel()`.

---

### [MÉDIO] `DEFAULT_DDD` é alias de backward-compat proibido

**Dimensão:** Convenções / Zero backward-compat aliases
**Arquivo:** `framework/shopman/web/constants.py:19-20`

```python
# Kept for backwards compat — views should prefer get_default_ddd()
DEFAULT_DDD = _DEFAULT_DDD_FALLBACK
```

A convenção explícita do projeto proíbe aliases de backward-compat. `DEFAULT_DDD` é exatamente esse padrão.

**Correção sugerida:** Verificar se `DEFAULT_DDD` ainda é referenciado. Se não, remover. Se sim, migrar callers para `get_default_ddd()` e remover o alias.

---

### [MÉDIO] `delivery_address_id` não documentado em data-schemas.md

**Dimensão:** Contratos de camadas
**Arquivo:** `framework/shopman/web/views/checkout.py`, `framework/shopman/services/checkout_defaults.py`, `docs/reference/data-schemas.md`

A chave `delivery_address_id` é escrita em `session.data` por views de checkout e lida por `checkout_defaults.py`, mas está ausente de `data-schemas.md`. A governança do projeto exige documentação antes do uso.

**Correção sugerida:** Documentar em `data-schemas.md` como chave de `Session.data` (write: CheckoutView, read: checkout_defaults — somente para inferência de defaults, não propagada ao Order.data).

---

### [MÉDIO] `emit_event()` calcula seq sem lock — race condition possível

**Dimensão:** Concorrência
**Arquivo:** `packages/omniman/shopman/omniman/models/order.py:254-257`

`emit_event()` calcula `last_seq = self.events.aggregate(Max("seq"))["m"]` sem `select_for_update`. Dois threads concorrentes podem calcular o mesmo `last_seq` e violar `UniqueConstraint(fields=["order", "seq"])`, lançando `IntegrityError`. `transition_status()` usa `select_for_update()` corretamente, mas `emit_event()` não.

A correção de WP-DS-9 adicionou proteção parcial com `except IntegrityError` + retry em `emit_event`, mas a causa raiz (ausência de lock no SELECT MAX) permanece.

**Correção sugerida:** Adicionar `select_for_update()` na query do MAX dentro de um `transaction.atomic()`, ou migrar para `auto_increment` de banco para seq.

---

### [BAIXO] Residuais de nomes antigos em comentários (AF-7 incompleto)

**Dimensão:** Nomenclatura
**Arquivos:**
- `framework/shopman/management/commands/seed.py` — `# Offering`, `# Stocking`, `# Crafting`, `# Ordering` em comentários de seção
- `framework/shopman/modifiers.py:4` — docstring: "Modifiers follow the Ordering Modifier protocol"
- `framework/shopman/middleware.py:18` — docstring: "propagated to Ordering.Session.data"

**Correção sugerida:** Substituir `Offering→Offerman`, `Stocking→Stockman`, `Crafting→Craftsman`, `Ordering→Omniman` nos comentários afetados.

---

### [BAIXO] `onclick` em offline.html sem comentário de exceção

**Dimensão:** Frontend
**Arquivo:** `framework/shopman/templates/storefront/offline.html:65`

```html
<button class="retry-btn" onclick="window.location.reload()">
```

A convenção proíbe `onclick=`. O caso é tecnicamente justificável (template PWA offline — Alpine.js não está disponível), mas não está documentado como exceção explícita. CLAUDE.md lista "IntersectionObserver e APIs do browser que não têm equivalente Alpine" como exceção, mas não menciona o template offline explicitamente.

**Correção sugerida:** Adicionar comentário `<!-- PWA offline: Alpine não carregado, onclick é intencional -->` ou converter para Alpine com Alpine carregado inline.

---

## Itens verificados sem achados

- `KNOWN_CONFIG_KEYS` e referências a `pipeline` em `channel.py`: OK — removidos.
- Tópicos fiscais em `services/fiscal.py`: OK — usa `FISCAL_EMIT_NFCE`/`FISCAL_CANCEL_NFCE`.
- Mock de backend fiscal/accounting em `handlers/__init__.py`: OK — `_load_optional_backend()` retorna `None` quando não configurado, sem fallback para mocks.
- `order_id` na resposta do `CommitService`: OK — retorna apenas `order_ref`.
- `data-schemas.md` com `intent_id`: OK — toda a documentação usa `intent_ref`.
- `kds.py` e `pedidos.py` com `delivery_method`: OK — ambos usam `get_fulfillment_type()`.
- `_channel_config` helper em `flows.py`: OK — removido, usa `_effective_config(order)`.
- `_pop_matching_hold` em `stock.py`: OK — substituído por `_adopt_holds_for_qty`.
- `on_payment_confirm` em webhooks: OK — `efi.py` e `stripe.py` usam `dispatch(order, "on_paid")`.
- Exposição de PK em API: OK — `CheckoutResponseSerializer` tem apenas `order_ref` e `status`.
- Importações de `instances/` no framework: OK — zero ocorrências.
- Campos monetários sem sufixo `_q`: OK — nenhum campo BigIntegerField/IntegerField monetário sem `_q`.
- `CHANNEL_REF` hardcoded em `cart.py`: OK — lê de settings.
- `Recipe.code` e `WorkOrder.code`: Exceções deliberadas documentadas em CLAUDE.md.
