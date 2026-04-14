# Auditoria Kernel + Framework — 2026-04-10

**Escopo:** kernel (`packages/`, 8 packages) e framework (`framework/shopman/`).
**Objetivo:** identificar vazamentos do framework para o kernel, resíduos de migrações
de naming, duplicações de caminho, código morto, e tudo o que precisa ser limpo antes
de reestruturar a arquitetura do framework.
**Método:** três varreduras paralelas (Explore agents) + verificação manual dos
achados críticos. Zero modificações de código.

> Esta auditoria é a entrada do plano de reestruturação que vem a seguir.
> Cada achado deve virar uma decisão (corrigir / aceitar / mover) durante o plano.

---

## 0. Sumário Executivo

| # | Achado | Severidade | Categoria |
|---|--------|-----------|-----------|
| C1 | Admin do omniman referencia campos `Channel.config` e `Channel.flow` removidos — quebra ao abrir Channel no admin | 🔴 Bloqueante | Resíduo de migração |
| C2 | `handlers/customer.py` (344 linhas) é duplicação literal de `services/customer.py` (302 linhas) — duas implementações vivas da mesma resolução de cliente | 🔴 Crítico | Caminho duplicado |
| C3 | Framework filtra `Hold.objects.filter(metadata__reference=...)` em 5 lugares — acopla framework a chave interna do JSONField do stockman | 🔴 Crítico | Vazamento kernel |
| C4 | 28 imports profundos do framework para `shopman.guestman.contrib.*` (preferences, identifiers, timeline, insights, loyalty, consent) | 🔴 Crítico | Vazamento kernel |
| C5 | 13 dos 21 campos do `ChannelConfig` jamais são lidos em runtime — toda a aposta declarativa é decorativa | 🟠 Alto | Código morto |
| C6 | 2 handlers órfãos: `customer.ensure` e `checkout.infer_defaults` registrados mas nunca enfileirados | 🟠 Alto | Código morto |
| C7 | `framework/shopman/checks.py:140` filtra `Channel.objects.filter(config__fiscal__enabled=True)` — campo `config` não existe mais | 🟠 Alto | Resíduo de migração |
| C8 | Resíduo massivo de naming antigo (`Stocking`, `Crafting`, `Offering`) em docstrings, AppConfig classes, settings dataclasses, `__init__.py`, `pyproject.toml` de TODOS os packages | 🟠 Alto | Resíduo de migração |
| C9 | 8 arquivos `*_test_settings.py` com nomes de personas antigas em `packages/*/` | 🟠 Alto | Resíduo de migração |
| C10 | `craftsman/contrib/stocking/` deveria chamar-se `stockman/` (resíduo de naming) | 🟡 Médio | Resíduo de migração |
| C11 | Framework define `CustomerBackend` Protocol em `protocols.py` com `code:` (convenção antiga) — duplicado e morto. Guestman tem o correto com `ref:` | 🟡 Médio | Protocol fantasma |
| C12 | Framework hardcoded a Nelson em `seed.py`, `fiscal.py` e templates — quebra agnosticidade de instância | 🟡 Médio | Vazamento de instância |
| C13 | 15 padrões `try: from shopman.X except ImportError: pass` — escondem dependências obrigatórias como opcionais | 🟡 Médio | Acoplamento disfarçado |
| C14 | Status de pagamento lido de `order.data["payment"]` em vários pontos do framework — viola regra "Payman é canônico" | 🟡 Médio | Vazamento conceitual |
| C15 | Múltiplos imports de `shopman.<package>.models.<sub>` (enums, position, device_trust) — fronteira pública não respeitada | 🟡 Médio | Vazamento kernel |
| C16 | Campos `Channel.pricing_policy` e `Channel.edit_policy` consumidos só pelo framework (testes do kernel à parte) — suspeitos de "escapar" do framework para o kernel | 🟡 Médio | Vazamento reverso |
| C17 | `payman.protocols.PaymentBackend` não tem implementador no kernel — só faz sentido com o framework presente | 🟢 Baixo | Protocol borderline |

**Status do kernel:** o que mais preocupa **não** é o que parece à primeira vista.
Os imports inversos (kernel→framework) são **zero**. Os Protocols principais
(SkuValidator, ProductionBackend, InventoryProtocol, CatalogProtocol, DemandProtocol,
CostBackend, ProductInfoBackend, CustomerResolver) estão **vivos** e têm
implementadores reais no próprio kernel. Imports cruzados entre packages são
todos **legítimos** (adapters injetáveis, lazy imports, noop fallbacks). A
fundação está intacta.

**O dano real está em três frentes:**

1. **Resíduo de migração de naming não terminada** (C1, C7, C8, C9, C10) —
   espalhado em quase todo lugar, é trabalho mecânico mas grande.
2. **Vazamentos do framework para o kernel via JSONField mágico e contrib**
   (C3, C4, C15, C16) — mais sério estruturalmente, exige API pública nos
   packages para resolver direito.
3. **Caminho duplicado, código morto, contratos não obedecidos no framework**
   (C2, C5, C6, C11, C13, C14) — exatamente o "framework bagunçado, mexido por
   partes" que motivou esta auditoria.

---

## 1. Bloqueantes (precisam ser corrigidos antes de qualquer outra coisa)

### C1 — Admin do omniman quebra ao abrir Channel

**Arquivo:** `packages/omniman/shopman/omniman/admin.py`

A migração `0008_channel_kind_remove_listing_ref_config.py` removeu o campo
`Channel.config` e renomeou `flow` para `kind`. Mas o ChannelAdmin nunca foi
atualizado:

| Linha | Resíduo | Consequência |
|------:|---------|--------------|
| 171 | `(_("Identidade"), {"fields": ("name", "ref", "flow"), "classes": ("tab",)})` | `flow` não existe — admin quebra |
| 178 | `{"fields": ("config_flow_display",), "classes": ("tab",)}` | OK (display method), mas o método lê `obj.config` |
| 182 | `{"fields": ("display_order", "config_display", "config", "is_active"), "classes": ("tab",)}` | `config` não existe — admin quebra |
| 186 | `readonly_fields = ("created_at", "config_display", "config_flow_display")` | OK em si, mas os métodos quebram |
| 191 | `if obj and obj.config:` | AttributeError |
| 207 | `if not obj or not obj.config:` | AttributeError |
| 210 | `c = obj.config` | AttributeError |
| 257 | `flow = c.get("flow", {})` | encadeado ao 210 |
| 312 | `formatted = json.dumps(obj.config, ...)` | AttributeError |
| 316 | `return str(obj.config)` | AttributeError |
| 321 | `if "config" in form.base_fields:` | OK em runtime (False), mas é morto |

**Decisão para o plano:** o admin de Channel precisa ser reescrito para:
(a) ler do `ChannelConfigRecord` (que vive no framework, não no kernel);
(b) ou simplesmente perder a aba "config" e deixar o framework expor seu próprio
admin de configuração de canal. Sugestão: **(b)** — o kernel não deve saber
sobre `ChannelConfig`, nem indiretamente.

---

## 2. Caminhos duplicados (responsabilidade com 2+ implementações vivas)

### C2 — `handlers/customer.py` é cópia de `services/customer.py`

**Verificado manualmente:**
- `framework/shopman/services/customer.py` — 302 linhas
- `framework/shopman/handlers/customer.py` — 344 linhas

Ambos contêm:
- `_handle_manychat`, `_handle_ifood`, `_handle_phone` (com `_handle_balcao` adicional no handler)
- `_split_name`, `_normalize_phone_safe`, `_find_by_identifier`, `_add_identifier`
- Lógica idêntica linha-a-linha de resolução de cliente, save de delivery address,
  criação de timeline event, recálculo de insights

**Quem chama o quê:**
- `services/customer.ensure(order)` é chamado **diretamente** em `flows.py:99, 191, 282`
- `handlers/customer.CustomerEnsureHandler` é registrado em `handlers/__init__.py:116`
  para o tópico `customer.ensure` — **mas nenhum lugar do framework cria essa
  Directive** (handler órfão, ver C6)

**Conclusão:** o handler está duplicando código vivo do service e nunca é
exercitado em produção. Bug encontrado num lugar não é corrigido no outro. É
o exemplo mais puro de "blotted, truncated, mexido por partes" que existe no
framework.

### Outros caminhos múltiplos identificados

| Responsabilidade | Lugar 1 | Lugar 2 | Lugar 3 | Status |
|-----------------|---------|---------|---------|--------|
| Criar fulfillment | `services/fulfillment.create(order)` | `handlers/fulfillment.FulfillmentCreateHandler` | — | Handler delega ao service (versão atual). Mas a flag `order.data["fulfillment_created"]` é setada nos dois. |
| Status de pagamento | `services/payment.py` (consulta Payman) | `handlers/notification.py:_get_payment_status` (consulta Payman) | `web/views/checkout.py:442` (lê `order.data["payment"]["intent_ref"]`) | Inconsistente — a view infere por presença de chave. |
| Customer creation | `services/customer.py` | `handlers/customer.py` | `web/views/checkout.py:404` (lê customer pós-commit, não cria) | Ver C2. View atual só lê. |

---

## 3. Vazamentos do framework para o kernel

### C3 — `Hold.metadata__reference` em 5 lugares

O framework filtra holds usando uma chave interna do JSONField do stockman.
Não há API explícita; cada call site replica o `metadata__reference=session_key`.

| Arquivo | Linha | Padrão |
|---------|------:|--------|
| `framework/shopman/services/availability.py` | 508 | `Hold.objects.filter(metadata__reference=session_key, sku=sku, status__in=[...])` |
| `framework/shopman/services/stock.py` | 214 | `Hold.objects.filter(metadata__reference=session_key, status__in=[...])` |
| `framework/shopman/adapters/stock.py` | 227 | `Hold.objects.filter(status__in=[...], metadata__reference=reference)` |
| `framework/shopman/web/views/cart.py` | 341 | `Hold.objects.filter(metadata__reference=session_key).active()` |
| `framework/shopman/web/views/checkout.py` | 758 | `Hold.objects.filter(metadata__reference=session_key).active()` |

Pior: `services/stock.py` em ~líneas 200-260 também faz parsing manual de `hold_id`
para recuperar pk, lê `metadata`, regrava `metadata`, etc. — manipulação direta
do interno do stockman.

**Decisão para o plano:** o stockman precisa expor uma API pública do tipo
`StockmanService.find_holds_by_reference(ref) -> QuerySet[Hold]` (ou método de
domínio análogo). Nenhuma view ou service do framework deve falar com `Hold`
direto. Esta é uma das poucas mudanças no kernel que vale fazer — é adicionar
API, não esconder coisa.

### C4 — 28 imports profundos do framework para `guestman.contrib.*`

Os contribs do guestman são tratados como API pública pelo framework, com
`try/ImportError` em todo lugar para fingir que são opcionais. Distribuição
dos 28 imports:

| Contrib | Imports do framework | Arquivos do framework |
|---------|----------------------|------------------------|
| `preferences` | 9 | `services/checkout_defaults.py`, `web/views/account.py` |
| `identifiers` | 6 | `services/customer.py`, `handlers/customer.py` |
| `loyalty` | 5 | `handlers/loyalty.py`, `web/views/account.py`, `web/views/checkout.py` |
| `timeline` | 2 | `services/customer.py`, `handlers/customer.py` |
| `insights` | 4 | `services/customer.py`, `handlers/customer.py`, `web/views/_helpers.py` |
| `consent` | 2 | `web/views/account.py` |

**Conclusão:** o framework não vive sem esses contribs. Tratar como opcional é
fingimento. As opções honestas são:
1. **Mover os contribs para o framework** — eles existem por causa dele.
2. **Aceitar como API pública do guestman** — documentar, expor via `guestman.preferences`, etc., remover os `try/ImportError`.

Discussão pendente — o usuário sinalizou indecisão. Decisão entra no plano.

### C15 — Imports de submódulos internos do kernel

Além de contribs, o framework também alcança submódulos internos de outros
packages:

| Arquivo | Import | Risco |
|---------|--------|-------|
| `framework/shopman/services/availability.py:503` | `shopman.stockman.models.enums` | Enum interno |
| `framework/shopman/services/stock.py:209` | `shopman.stockman.models.enums` | Idem |
| `framework/shopman/adapters/stock.py:170, 221` | `shopman.stockman.models.enums` | Idem |
| `framework/shopman/handlers/_stock_receivers.py:21` | `shopman.stockman.models.enums` | Idem |
| `framework/shopman/management/commands/cleanup_d1.py:10` | `shopman.stockman.models.position` | Submodelo |
| `framework/shopman/web/views/production.py:18` | `shopman.stockman.models.position` | Idem |
| `framework/shopman/admin/dashboard.py:452` | `shopman.stockman.models.position` | Idem |
| `framework/shopman/web/views/closing.py:22` | `shopman.stockman.models.position` | Idem |
| `framework/shopman/web/views/devices.py:67, 107` | `shopman.doorman.models.device_trust` | Submodelo |
| `framework/shopman/services/alternatives.py:27` | `shopman.offerman.contrib.suggestions` | Contrib privado |

**Decisão para o plano:** cada package do kernel deve definir o que é público
no `__init__.py` (re-export explícito) e o framework deve passar a importar
**só** dessas superfícies. Imports profundos viram erro de lint.

### C16 — Campos `Channel.pricing_policy` e `Channel.edit_policy` são framework-only

Esses campos só são lidos por `framework/shopman/web/cart.py`, `web/views/pos.py`
e `seed.py`. O kernel omniman não os consulta em nenhum lugar produtivo (só em
testes). Eles parecem ter sido adicionados ao kernel para resolver uma necessidade
do framework — exatamente o tipo de "espirro" que o usuário queria identificar.

**Decisão para o plano:** mover essas duas políticas para `ChannelConfig` (no
framework). O `Channel` do kernel volta a ter só `name`, `ref`, `kind`,
`is_active`, `display_order` — o mínimo identificável.

### C14 — `order.data["payment"]` lido como espelho de status

A regra declarada (`docs/reference/data-schemas.md`, `services/payment.py:11`) é
que status de pagamento é canônico em Payman. Mas:

| Arquivo | Linha | Padrão |
|---------|------:|--------|
| `framework/shopman/web/views/checkout.py` | 442 | `payment = (order.data or {}).get("payment", {}); if payment.get("intent_ref"): ...` |
| `framework/shopman/handlers/loyalty.py` | 25 | `order.data["loyalty"]["redeem_points_q"]` (não pagamento, mas mesmo padrão) |
| `framework/shopman/handlers/fulfillment.py` | 68, 77 | `order.data["fulfillment_created"]` (flag mágica) |
| `framework/shopman/handlers/fiscal.py` | 52-55 | `order.data["nfce_*"]` (flags mágicas) |

A versão atual de `handlers/notification.py:259` (`_get_payment_status`)
**está correta** — consulta Payman via `PaymentService.get(intent_ref).status`.
Mas o padrão de "infere por presença de chave" continua espalhado.

**Decisão para o plano:** estabelecer regra "`order.data["payment"]` contém só
`intent_ref`, `method`, `amount_q` e — quando captura ocorre — um snapshot
imutável `captured: {transaction_id, captured_at, gateway}`. Status atual é
**sempre** consultado em Payman. Teste de invariante para impedir regressão.

---

## 4. Código morto / contratos não obedecidos

### C5 — 13 dos 21 campos de `ChannelConfig` jamais são lidos

| Campo | Lido em runtime? |
|-------|:---:|
| `Confirmation.mode` | ✅ |
| `Confirmation.timeout_minutes` | ✅ |
| `Payment.method` (via `available_methods`) | ✅ |
| `Payment.timeout_minutes` | ✅ (validação) |
| `Stock.hold_ttl_minutes` | ❌ |
| `Stock.safety_margin` | ❌ |
| `Stock.planned_hold_ttl_hours` | ❌ |
| `Stock.allowed_positions` | ❌ |
| `Notifications.backend` | ✅ |
| `Notifications.fallback_chain` | ❌ |
| `Notifications.routing` | ❌ |
| `Rules.validators` | ✅ (parcial — só `_helpers.py:643` para `shop.minimum_order`) |
| `Rules.modifiers` | ❌ |
| `Rules.checks` | ❌ |
| `Flow.transitions` | ❌ |
| `Flow.terminal_statuses` | ❌ |
| `Flow.auto_transitions` | ❌ |
| `Flow.auto_sync_fulfillment` | ✅ (`handlers/fulfillment.py:178`) |
| `handle_label` | ✅ (context_processors) |
| `handle_placeholder` | ✅ (context_processors) |

A interpretação correta — confirmada na conversa que precedeu esta auditoria —
é que **o desenho de `ChannelConfig` está certo** (decomposição aspectual,
cascata, validação). O que está errado é **o consumo**: o runtime ainda é
imperativo (subclasses de Flow) e ignora a maior parte do que a config oferece.
A reescrita do runtime resolve C5.

### C6 — Handlers órfãos

| Handler | Topic | Registrado em | Algum lugar cria a Directive? |
|---------|-------|---------------|------------------------------|
| `CustomerEnsureHandler` | `customer.ensure` | `handlers/__init__.py:116` | ❌ Nada no framework cria |
| `CheckoutInferDefaultsHandler` | `checkout.infer_defaults` | `handlers/__init__.py:168` | ❌ Nada no framework cria |

Ambos foram registrados num momento em que se imaginou ter pipeline assíncrono
pós-commit, e nunca foram conectados.

**Decisão para o plano:** a regra deve ser "nenhum handler em `ALL_HANDLERS` sem
pelo menos um produtor identificado". Isso vira teste de invariante.

### C11 — `CustomerBackend` Protocol fantasma no framework

`framework/shopman/protocols.py:91` define um `CustomerBackend` Protocol com
métodos que usam `code:` (convenção antiga). Ninguém implementa, ninguém consome.
O guestman tem o equivalente correto em
`packages/guestman/shopman/guestman/protocols/customer.py:20` com `ref:`.

O framework não usa nenhum dos dois — fala com customer via `services/customer.py`
direto. O Protocol no framework é puro fóssil arqueológico.

### C13 — `try: from shopman.X except ImportError: pass` em 15 lugares

Padrão usado para fingir que dependências obrigatórias do framework são
opcionais. Lista parcial:

| Arquivo | Linhas | Import | Real status |
|---------|--------|--------|-------------|
| `framework/shopman/handlers/pricing.py` | 17, 47, 56 | `shopman.offerman.*` | **Crítico** — pricing sem catalog não funciona |
| `framework/shopman/web/constants.py` | 30 | `shopman.stockman.services.availability` | **Crítico** |
| `framework/shopman/web/views/cart.py` | 337 | `shopman.stockman.models.Hold` | **Crítico** |
| `framework/shopman/web/views/checkout.py` | 755 | `shopman.stockman.models.Hold` | **Crítico** |
| `framework/shopman/handlers/_stock_receivers.py` | 19 | `shopman.stockman.models` | **Crítico** |
| `framework/shopman/handlers/__init__.py` | 104 | `shopman.adapters.notification_sms` | OK (de fato opcional) |
| `framework/shopman/handlers/__init__.py` | 211 | `shopman.craftsman.signals` | Aceitável — produção é opcional |

**Decisão para o plano:** os imports realmente opcionais ficam com guard. Os
imports obrigatórios viram imports normais. Se faltar a dependência, o app
**falha no boot** com mensagem clara — nunca em runtime.

---

## 5. Resíduos de migração de naming (Stocking/Crafting/Offering/etc.)

### C8 — Resíduo nos packages do kernel

A regra `feedback_persona_names_only` exige zero ocorrências de `Stocking`,
`Crafting`, `Offering`, `Ordering`, `Identification`, `Customers`, `Payments`,
`Auth/Doorkeeper` como nomes de persona. A realidade:

#### stockman
- `packages/stockman/shopman/stockman/__init__.py:2` — `"Django Stocking — Motor Unificado de Estoque."`
- `packages/stockman/shopman/stockman/apps.py:5` — `class StockingConfig(AppConfig):`
- `packages/stockman/shopman/stockman/conf.py:2,20,21,36,39,41` — `class StockingSettings`, `get_stocking_settings()`
- `packages/stockman/shopman/stockman/signals.py:2` — `"Stocking signals — domain events..."`
- `packages/stockman/shopman/stockman/exceptions.py:2` — `"Exceptions for Stocking."`
- `packages/stockman/shopman/stockman/admin.py:2` — `"Stocking Admin..."`
- `packages/stockman/shopman/stockman/management/__init__.py:1` — `"""Stocking management commands."""`
- `packages/stockman/shopman/stockman/management/commands/__init__.py:1` — idem
- `packages/stockman/shopman/stockman/models/__init__.py:2` — `"Stocking Models."`
- `packages/stockman/shopman/stockman/models/enums.py:2` — `"Enums for Stocking models."`
- `packages/stockman/shopman/stockman/contrib/__init__.py:1` — `"""Stocking contrib modules."""`
- `packages/stockman/shopman/stockman/contrib/alerts/conf.py:1` — `"""Stocking Alerts configuration."""`
- `packages/stockman/shopman/stockman/contrib/alerts/__init__.py:2,6` — `"Stocking Alerts Dispatch..."`, `"...via Ordering..."`
- `packages/stockman/shopman/stockman/contrib/alerts/handlers.py:98,100,129` — múltiplas referências a `Ordering`
- `packages/stockman/shopman/stockman/contrib/alerts/apps.py:1,9` — `class StockingAlertsConfig`
- `packages/stockman/shopman/stockman/contrib/admin_unfold/__init__.py:1` — `"""Stocking Admin..."""`
- `packages/stockman/shopman/stockman/contrib/admin_unfold/apps.py:5` — `class StockingAdminUnfoldConfig`
- `packages/stockman/shopman/stockman/contrib/admin_unfold/admin.py:2,4` — docstrings
- `packages/stockman/shopman/stockman/adapters/__init__.py:2` — `"Stocking Adapters."`
- `packages/stockman/shopman/stockman/adapters/sku_validation.py:2` — `"Stocking Offering Adapter — SKU validation via Offering."` *(renomeado de `offering.py` — P0)*
- `packages/stockman/shopman/stockman/adapters/production.py:2` — `"Crafting Backend."` `"Implements ProductionBackend using Crafting's API"` *(renomeado de `crafting.py` — P0)*
- `packages/stockman/shopman/stockman/protocols/production.py:4-10` — `"Stocking to interact with..."` + comentário "Vocabulary mapping (Stocking → Crafting)"
- `packages/stockman/shopman/stockman/tests/__init__.py:1` — `"""Tests for Django Stocking."""`
- `packages/stockman/shopman/stockman/tests/conftest.py:2` — `"Pytest fixtures for Stocking tests."`
- `packages/stockman/pyproject.toml:8` — `description = "Shopman Stocking — Inventory Management"`
- `packages/stockman/stocking_test_settings.py` — arquivo inteiro com nome antigo

#### craftsman
- `packages/craftsman/shopman/craftsman/apps.py:5` — `class CraftingConfig(AppConfig):`
- `packages/craftsman/shopman/craftsman/views.py:2` — `"Crafting Views (vNext)."`
- `packages/craftsman/shopman/craftsman/services/scheduling.py:2` — comentário menciona "Stocking"
- `packages/craftsman/shopman/craftsman/protocols/inventory.py:2-7` — múltiplas ocorrências
- `packages/craftsman/pyproject.toml:8` — `description = "Shopman Crafting — Production Management (MRP)"`
- `packages/craftsman/crafting_test_settings.py` — arquivo
- `packages/craftsman/shopman/craftsman/contrib/stocking/` — **diretório** com nome antigo (ver C10)

#### offerman
- `packages/offerman/shopman/offerman/__init__.py:2` — `"Shopman Offering - Product Catalog."`
- `packages/offerman/shopman/offerman/apps.py:5` — `class OfferingConfig(AppConfig):`
- `packages/offerman/shopman/offerman/conf.py:2,21` — `class OfferingSettings`
- `packages/offerman/pyproject.toml:8` — `description = "Shopman Offering — Product Catalog"`
- `packages/offerman/offering_test_settings.py` — arquivo

#### omniman
- `packages/omniman/shopman/omniman/protocols.py:9` — comentário menciona "Stocking"
- `packages/omniman/ordering_test_settings.py` — arquivo

#### guestman
- `packages/guestman/shopman/guestman/migrations/0001_initial.py:49` — help_text "Código do Listing no Offering"
- `packages/guestman/shopman/guestman/models/group.py:10,15,20` — `# Identification`, `# Link to pricing (Offering Listing)`, help_text com "Offering"
- `packages/guestman/shopman/guestman/models/customer.py:42` — `# Identification (ref + uuid pattern...)`
- `packages/guestman/shopman/guestman/models/contact_point.py:46` — `# Identification`
- `packages/guestman/shopman/guestman/models/external_identity.py:36` — `# Identification`
- `packages/guestman/shopman/guestman/services/customer.py:130` — `"""Return customer's listing_ref (for Offering pricing)."""`
- `packages/guestman/shopman/guestman/admin.py:146` — fieldset label `"Identification"`
- `packages/guestman/shopman/guestman/contrib/admin_unfold/admin.py:140` — idem
- `packages/guestman/customers_test_settings.py` — arquivo

#### payman
- `packages/payman/shopman/payman/__init__.py:2` — `"Shopman Payments — Payment Lifecycle Management."`
- `packages/payman/shopman/payman/apps.py:5` — `class PaymentsConfig(AppConfig):`
- `packages/payman/pyproject.toml:8` — `description = "Shopman Payments — Payment Intents & Transactions"`
- `packages/payman/payments_test_settings.py` — arquivo

#### doorman
- `packages/doorman/shopman/doorman/__init__.py:2` — `"Shopman Auth — Phone-First Authentication."`
- `packages/doorman/shopman/doorman/apps.py:9` — `class AuthConfig(AppConfig):`
- `packages/doorman/pyproject.toml:8` — `description = "Shopman Gating — Phone-First Authentication"`
- `packages/doorman/auth_test_settings.py` — arquivo

### C9 — Arquivos `*_test_settings.py` com nomes antigos

```
packages/craftsman/crafting_test_settings.py
packages/doorman/auth_test_settings.py
packages/guestman/customers_test_settings.py
packages/offerman/offering_test_settings.py
packages/omniman/ordering_test_settings.py
packages/payman/payments_test_settings.py
packages/stockman/stocking_test_settings.py
packages/utils/utils_test_settings.py    ← este aqui é OK (nome correto)
```

7 a renomear, 1 já correto.

### C10 — `craftsman/contrib/stocking/` deveria ser `stockman/`

Confirmado: `packages/craftsman/shopman/craftsman/contrib/stocking/` existe e tem
dentro `production.py`, `handlers.py`, `apps.py`, `management/`. É o adapter
craftsman→stockman, então o nome correto pela convenção persona é
`craftsman/contrib/stockman/`.

### Resíduos de naming antigo no framework

| Arquivo | Linha | Padrão |
|---------|------:|--------|
| `framework/shopman/handlers/customer.py` | 4 | `# Inline de shopman.identification.handlers.` |
| `framework/shopman/services/production.py` | 23 | `# O Stocking reage ao signal...` |
| `framework/shopman/protocols.py` | (comentário) | `# Customer (inline — era shopman.identification.protocols)` |
| `framework/shopman/web/constants.py` | 15-16, 19-20 | `HAS_STOCKING` (variável + lógica) |
| `framework/shopman/web/cart.py` | 269 | `HAS_STOCKING` (uso) |
| `framework/shopman/context_processors.py` | 72 | comentário "Ordering session" |
| `framework/shopman/rules/validation.py` | 107 | `OrderingValidationError` (alias antigo) |

### C7 — `framework/shopman/checks.py:140`

Verificado: linha 140 contém `Channel.objects.filter(config__fiscal__enabled=True)`.
O campo `Channel.config` foi removido na migração 0008. O check sempre vai
explodir (ou silenciosamente retornar zero) quando executado em produção.

---

## 6. Vazamentos de instância

### C12 — Hardcoded a Nelson em vários lugares do framework

| Arquivo | Linha | Padrão |
|---------|------:|--------|
| `framework/shopman/fiscal.py` | 16 | `"nelson.adapters.fiscal_focus.FocusNFCeBackend"` em string |
| `framework/shopman/management/commands/seed.py` | 1744 | `promo_nelson10` |
| `framework/shopman/management/commands/seed.py` | 1784 | `promotion: promo_nelson10` |
| `framework/shopman/tests/web/test_web_pwa.py` | 99 | assertion com `"CACHE_NAME = 'nelson-v2'"` |

O `seed.py` é fundamentalmente um comando de instância (popula dados específicos
da Nelson Boulangerie). Sua presença no `framework/` é em si um vazamento. Decisão:
mover `seed.py` para `instances/nelson/management/commands/seed.py`. O framework
fica com no máximo um `seed_demo.py` genérico ou nenhum.

---

## 7. Protocols borderline

### C17 — `payman.protocols.PaymentBackend`

Definido em `packages/payman/shopman/payman/protocols.py:70`. Implementadores:
zero no kernel — só o framework provê implementações (efi, stripe, mock).

**Análise:** Diferente do `CustomerBackend` morto do framework, este Protocol
é **bem desenhado** e está no lugar certo. O fato de não ter implementador no
kernel é normal: payment gateways são integrações externas. Aceitar como está.

---

## 8. O que está saudável (não mexer)

Para evitar refatoração desnecessária, vale registrar o que **está bem**:

1. **Nenhum import inverso (kernel→framework).** Confirmado por busca exaustiva.
2. **Protocols principais do kernel todos vivos:**
   `SkuValidator`, `ProductionBackend`, `InventoryProtocol`, `CatalogProtocol`,
   `DemandProtocol`, `CostBackend`, `ProductInfoBackend`, `CustomerResolver` —
   todos com implementadores reais no próprio kernel.
3. **Imports cruzados entre packages do kernel são todos legítimos:**
   adapters injetáveis, lazy imports, noop fallbacks. Stockman↔Craftsman,
   Offerman↔Stockman, Doorman↔Guestman, etc.
4. **`omniman.contrib.refs`, `omniman.contrib.stock`, `stockman.contrib.alerts`,
   `stockman.contrib.admin_unfold`, `craftsman.contrib.demand`,
   `craftsman.contrib.admin_unfold`, `offerman.contrib.admin_unfold`,
   `offerman.contrib.import_export`** — todos saudáveis, consumo interno legítimo.
5. **Convenção `ref` vs `code`** está respeitada no kernel. Todas as ocorrências
   de `code` que vi são exceções legítimas (`Recipe.code` slug, `WorkOrder.code`
   sequencial, `Directive.error_code` status, `tracking_code` rastreio,
   `code_hash` em VerificationCode). A única violação é o `CustomerBackend`
   morto **no framework** (C11).
6. **Migrações antigas (`0002_rename_tables.py` em doorman, etc.)** — testemunho
   histórico saudável da renomeação, não bloqueante.
7. **`omniman.services.commit.CommitService`** — bem desenhado, com comentário
   explícito "Kernel não lê channel.config — o framework passa o config resolvido
   como parâmetro". Esse é o padrão correto que outros lugares deveriam seguir.

---

## 9. Decisões pendentes (entram no plano de reestruturação)

Estas decisões **não** podem ser tomadas pela auditoria — exigem alinhamento
com o usuário durante o plano:

1. **C4: contribs do guestman ficam no kernel ou movem para o framework?**
   Adiar até depois que o framework estiver limpo (recomendação prévia).
2. **C16: `pricing_policy` e `edit_policy` saem do `Channel` do kernel?**
   Provável sim, mas é mexer no kernel — cuidado.
3. **`production_flows.py` continua existindo separado de `flows.py`?**
   (Ver auditoria anterior — engole exceções, registry paralelo, filosofia
   divergente.) Decisão: unificar ou manter explicitamente separado com
   justificativa.
4. **`framework/shopman/protocols.py` ainda tem razão de existir?**
   Hoje só re-exporta de payman/omniman e define um `CustomerBackend` morto.
   Talvez devesse sumir.

---

## 10. Próximos passos

1. Esta auditoria entra como referência fixa do plano de reestruturação.
2. O plano será dividido em **workpackages auto-contidos**, cada um com prompt
   próprio que cita esta auditoria como entrada.
3. Ordem sugerida (sujeita a revisão):
   - **WP-A (kernel hygiene):** corrigir C1, C7, C8, C9, C10. Trabalho mecânico,
     sem risco de design. Deixa o kernel realmente sagrado.
   - **WP-B (framework runtime):** reescrever flows + services + handlers.
     Resolve C2, C5, C6, C11, C13, C14. **A reescrita conceitual.**
   - **WP-C (kernel API publication):** stockman expõe API de busca de holds
     (resolve C3), packages do kernel publicam superfície explícita
     (resolve C15). Pequeno toque no kernel, alto retorno.
   - **WP-D (channel config consolidation):** mover `pricing_policy` /
     `edit_policy` para `ChannelConfig`, reescrever ChannelAdmin no framework
     (resolve C16, complementa C1).
   - **WP-E (instance separation):** mover `seed.py` e referências hardcoded
     a Nelson (resolve C12).
   - **WP-F (contribs decision):** pegar contrib por contrib do guestman,
     decidir mover ou manter (resolve C4). **Só depois das anteriores.**

Cada WP deve ter:
- Entrada: lista de itens da auditoria que resolve
- Saída: critérios objetivos de "feito"
- Prompt auto-contido para retomar em sessão limpa
- Testes que protegem o invariante após a mudança

---

## Addendum — P0 Naming Refactor (2026-04-14)

> Atualização pós-execução do plano `P0-NAMING-PLAN.md`.

### Itens resolvidos nesta auditoria

| # | Status | Notas |
|---|--------|-------|
| C1 | ✅ Corrigido | Admin de Channel reescrito em sessões anteriores |
| C7 | ✅ Corrigido | `checks.py` atualizado em sessões anteriores |
| C8 | ✅ Corrigido | **Todas** as ocorrências listadas foram limpas: docstrings, AppConfig classes, `conf.py`, `pyproject.toml`, `__init__.py`, adapters, protocols, signals, exceptions, admin, models, tests, contribs |
| C9 | ✅ Corrigido | Todos os 7 `*_test_settings.py` renomeados para `{package}_test_settings.py` canônico |
| C10 | ✅ Corrigido | `craftsman/contrib/stocking/` → `craftsman/contrib/stockman/` |

### Renames executados no P0 (2026-04-14)

**Adapters:**
- `stockman/adapters/offering.py` → `sku_validation.py`
- `stockman/adapters/crafting.py` → `production.py`
- `craftsman/adapters/stocking.py` → `stock.py`
- `craftsman/adapters/offering.py` → `catalog.py`
- `framework/adapters/offering.py` → `pricing.py`

**Templates:** `orderman/templates/ordering/` → `orderman/templates/orderman/`

**Testes de integração:**
- `test_crafting_offering.py` → `test_production_catalog.py`
- `test_crafting_stocking.py` → `test_production_stock.py`
- `test_crafting_app_integration.py` → `test_production_app_integration.py`
- `test_ordering_auth.py` → `test_session_auth.py`
- `test_ordering_attending.py` → `test_session_attending.py`

**Admin URLs:** `omniman_session_*` e `ordering_session_*` → `orderman_session_*`

**Throttle scopes:** `ordering_modify/commit` → `orderman_modify/commit`

**Funções internas:** `_stocking_available` → `_stockman_available`, `_crafting_available` → `_craftsman_available`

### Verificação: 821 passed, 17 skipped (suite completa)
