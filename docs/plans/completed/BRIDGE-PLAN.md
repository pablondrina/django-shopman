# BRIDGE-PLAN.md — Fechar a Distância Core ↔ App

Plano pós-hardening para que o App aproveite 100% do Core.
Contexto: HARDENING-PLAN 100% executado. Core pronto. App precisa alcançá-lo.

---

## Princípio

> "O Core está pronto — o App precisa alcançá-lo."

Três eixos:
1. **Limpar** — resíduos do desenvolvimento iterativo
2. **Conectar** — utilizar capacidades do Core que o App ignora
3. **Completar** — fechar loops operacionais para uso real

### Seed como Espelho

O seed (`shop/management/commands/seed.py`) deve refletir TODAS as capacidades
ativas. Cada WP que adiciona funcionalidade deve atualizar o seed para demonstrá-la.
Não adianta ativar bundles se o seed não cria pedidos com bundles.
Não adianta ativar BridgeToken se o seed não cria tokens de exemplo.

---

## WP-B1: Limpeza de Resíduos ✅ DONE

Corrigir lixo acumulado das iterações de desenvolvimento.

### Tarefas

1. **CHANNEL_CODE → CHANNEL_REF**
   - `channels/web/cart.py` line 13: `CHANNEL_CODE = "web"` → `CHANNEL_REF = "web"`
   - Find-replace global: toda referência a CHANNEL_CODE → CHANNEL_REF
   - Variável faz referência ao `Channel.ref`, não a um "code"

2. **Remover aliases backward-compat**
   - `channels/web/constants.py`: Remover `HAS_DOORMAN` e `HAS_STOCKMAN`
   - Substituir todos os usos por `HAS_AUTH` e `HAS_STOCKING` respectivamente
   - Convenção: "Zero backward-compat aliases" (CLAUDE.md)

3. **Registrar modifiers órfãos OU remover**
   - `shop/modifiers.py` define `EmployeeDiscountModifier` e `HappyHourModifier`
   - `channels/setup.py` NÃO os registra
   - Decisão: registrá-los condicionalmente (channel.config.rules.modifiers)
   - O HARDENING-PLAN previa que modifiers são ativados por canal via `rules.modifiers`
   - Setup deve registrar TODOS os modifiers disponíveis; o canal decide quais rodar

4. **Proteger MockPaymentConfirmView**
   - `channels/web/views/payment.py`: endpoint acessível sem guard
   - Adicionar: `if not settings.DEBUG: raise Http404`
   - Endpoint existe apenas para simular confirmação PIX em dev

5. **Eliminar confirmation_hooks.py como dispatcher redundante**
   - `hooks.py` é o dispatcher genérico (conectado ao signal via apps.py) ✓
   - `confirmation_hooks.py` tem 2 partes:
     a. Funções mortas (`on_order_created`, `on_order_status_changed`, `_on_cancelled`) → REMOVER
     b. `on_payment_confirmed()` — usada por webhooks.py → MOVER para hooks.py
   - Resultado: um único ponto de entrada para lifecycle hooks
   - Após mover, deletar `confirmation_hooks.py` inteiro

6. **Unificar campo de config de hold TTL**
   - `confirmation.py` usa `checkout_hold_expiration_minutes` (nome antigo)
   - `config.py` (ChannelConfig) define `Stock.hold_ttl_minutes` (nome correto)
   - Alinhar: `confirmation.py` deve ler de `ChannelConfig.effective(channel).stock.hold_ttl_minutes`
   - Eliminar referências a `checkout_hold_expiration_minutes` e `CONFIRMATION_FLOW` do settings

7. **Deletar orchestration.md (obsoleto)**
   - `docs/guides/orchestration.md` descreve a estrutura pré-hardening
   - Paths, nomes de módulos e organização estão todos desatualizados
   - Substituir por novo guia `docs/guides/channels.md` que reflita a estrutura real

8. **Rodar make test + make lint**

---

## WP-B2: Modifiers e Validators Config-Driven ✅ DONE

Fechar o loop: ChannelConfig.rules declara quais modifiers/validators ativar,
mas o mecanismo de filtragem não existe. Hoje TODOS os modifiers registrados rodam sempre.

### Contexto

O HARDENING-PLAN definiu:
```python
rules=ChannelConfig.Rules(
    validators=["business_hours", "min_order"],
    modifiers=["happy_hour", "employee_discount"],
    checks=["stock"],
)
```

Para isso funcionar, ModifyService precisa filtrar modifiers/validators pelo que o canal permite.

### Tarefas

1. **ModifyService: filtrar modifiers por config**
   - Ler `ChannelConfig.effective(channel).rules.modifiers`
   - Se a lista NÃO está vazia, só rodar modifiers cujo `code` está na lista
   - Se a lista está vazia, NÃO rodar nenhum (canal sem modifiers = limpo)
   - Se `rules.modifiers` é None (campo ausente), rodar todos (backward compat temporário)

2. **ModifyService: filtrar validators por config**
   - Mesma lógica com `rules.validators`

3. **Adicionar `code` a todos os modifiers e validators**
   - ItemPricingModifier: code = "pricing.item"
   - D1DiscountModifier: code = "d1_discount"
   - PromotionModifier: code = "promotion"
   - CouponModifier: code = "coupon"
   - SessionTotalModifier: code = "pricing.total"
   - EmployeeDiscountModifier: code = "employee_discount"
   - HappyHourModifier: code = "happy_hour"
   - BusinessHoursValidator: code = "business_hours"
   - MinimumOrderValidator: code = "min_order"

4. **Setup: registrar TODOS os modifiers/validators**
   - Incluir EmployeeDiscountModifier e HappyHourModifier
   - Incluir BusinessHoursValidator e MinimumOrderValidator (se existirem)
   - O canal decide quais ativar via config

5. **Presets: declarar modifiers nos presets**
   - Verificar que pos(), remote(), marketplace() declaram as rules corretas
   - pos: `modifiers=["employee_discount"]`
   - remote: `modifiers=["happy_hour"]`
   - marketplace: `modifiers=[]`

6. **Testes**
   - test_modifier_filtered_by_channel_config
   - test_empty_modifiers_list_runs_none
   - test_null_modifiers_runs_all (backward compat)
   - test_validator_filtered_by_channel_config

7. **make test + make lint**

---

## WP-B3: Pricing Cascade Completa ✅ DONE

O HARDENING-PLAN definiu uma cascata de preços: grupo do cliente → listing do canal → preço base.
Verificar e completar a implementação.

### Tarefas

1. **Verificar OfferingBackend** (channels/backends/pricing.py)
   - Deve implementar: grupo.listing_ref → channel.listing_ref → product.base_price_q
   - Se já implementado, verificar que funciona end-to-end

2. **CatalogPricingBackend vs OfferingBackend**
   - Se ambos existem, consolidar num único backend com cascata completa
   - O backend registrado no setup deve ser o que faz a cascata

3. **Catálogo filtra por listing do canal**
   - `channels/web/views/catalog.py` deve filtrar produtos pela listing do canal
   - Dois gates: produto ativo globalmente + produto ativo na listing do canal
   - Conforme HARDENING-PLAN seção "Catálogo do canal"

4. **Tiered pricing (min_qty) funcional**
   - ListingItem tem `min_qty` para preço por volume
   - CatalogService.unit_price() respeita tiers
   - Verificar que o storefront passa qty correta

5. **Testes**
   - test_price_cascade_group_over_channel_over_base
   - test_catalog_filtered_by_channel_listing
   - test_tiered_pricing_at_checkout

6. **make test + make lint**

---

## WP-B4: Integração Crafting ↔ App ✅ DONE

O Core de Crafting é um micro-MRP completo. O App quase não o usa.
Fechar os loops operacionais.

### Contexto (ADR-007)

O Crafting oferece: plan(), adjust(), close(), void(), suggest(), needs(), expected().
O App hoje só conecta signal `production_changed` → StockingBackend e `holds_materialized`.

### Tarefas

1. **Sugestão de produção no admin**
   - Criar view admin ou management command: `suggest_production`
   - Usa CraftService.suggest() com DemandBackend para gerar recomendações
   - Output: lista de recipes + quantidades sugeridas com base em histórico

2. **Consumo de ingredientes ao fechar WorkOrder**
   - CraftService.close() deve chamar StockingBackend para consumir ingredientes
   - Inventário: issue() para cada RecipeItem × qty produzida
   - Isso já é responsabilidade do InventoryProtocol do Crafting — verificar adapter

3. **Recebimento de produção no estoque**
   - Signal `production_changed` já conectado → StockingBackend deve chamar receive()
   - Verificar que o receiver cria Moves de entrada para o produto acabado

4. **Stock planning no pre-order**
   - Quando produto tem `availability_policy = "planned_ok"` e stock físico = 0
   - StockHoldHandler deve criar hold planejado (target_date futuro)
   - Quando produção se materializa (holds_materialized signal), hold vira físico
   - Verificar que este fluxo funciona end-to-end

5. **Testes de integração**
   - test_suggest_production_uses_demand_history
   - test_close_work_order_consumes_ingredients
   - test_production_creates_stock_moves
   - test_planned_hold_becomes_physical_on_production

6. **make test + make lint**

---

## WP-B5: Auth Completo no Storefront ✅ DONE

BridgeToken e DeviceTrust estão no Core mas não no App.

### Tarefas

1. **BridgeToken: endpoint de consumo no storefront**
   - Nova view: `BridgeLoginView` em `channels/web/views/auth.py`
   - URL: `/auth/bridge/<token>/`
   - Fluxo: recebe token → AuthBridgeService.consume(token) → cria session autenticada
   - Caso de uso: cliente no WhatsApp recebe link → abre web com sessão pré-autenticada
   - Redireciona para checkout ou account conforme `audience` do token

2. **DeviceTrust: skip-OTP em revisitas**
   - Após verificação OTP bem-sucedida, criar TrustedDevice via DeviceTrustService
   - Setar cookie seguro com device token
   - Em logins subsequentes: verificar cookie → se device confiável, skip OTP
   - Fluxo no auth view: check device → se trusted, auto-login → se not, pedir OTP

3. **Session-based auth real**
   - Hoje: phone-based lookup via POST param (frágil)
   - Implementar: após verificação, setar session vars (customer_uuid, verified=True)
   - Account views: verificar session, não POST param
   - Expiração: session timeout configurável

4. **Rate limiting em auth endpoints**
   - RequestCodeView: max 3 requests/phone/10min
   - VerifyCodeView: max 5 attempts/phone/10min
   - Usar Django cache framework (simples, sem deps extras)

5. **Testes**
   - test_bridge_token_creates_authenticated_session
   - test_bridge_token_expired_returns_error
   - test_device_trust_skips_otp
   - test_device_trust_expired_requires_otp
   - test_rate_limit_blocks_excessive_requests
   - test_session_auth_protects_account_views

6. **make test + make lint**

---

## WP-B6: Fulfillment, Bundles e Stock Alerts ✅ DONE

Fechar loops operacionais menores.

### Tarefas

1. **Bundle expansion no catálogo**
   - ProductDetailView: se produto é bundle, mostrar componentes via CatalogService.expand()
   - StockHoldHandler: ao reservar bundle, reservar componentes (não o bundle em si)
   - Verificar que expand() retorna componentes com qtys corretas

2. **Stock alerts funcionais**
   - StockAlert model já existe no Stocking core
   - Conectar signal post_save do Quant: quando qty < StockAlert.min_quantity → notificar
   - Usar NotificationSendHandler com template "stock_alert"
   - Destinatário: operador (configurável)

3. **Fulfillment tracking no storefront**
   - TrackingView já existe — verificar que mostra dados de Fulfillment model
   - Auto-enrich tracking URLs para Correios, Jadlog, Loggi (já implementado em handler)
   - Verificar que auto_sync_fulfillment funciona (fulfillment.dispatched → order.dispatched)

4. **Testes**
   - test_bundle_expansion_in_product_detail
   - test_bundle_stock_hold_reserves_components
   - test_stock_alert_triggers_notification
   - test_tracking_view_shows_fulfillment_data

5. **make test + make lint**

---

## WP-B7: Documentação Atualizada ✅ DONE

Alinhar docs com o estado real pós-hardening + bridge.

### Tarefas

1. **Deletar docs/guides/orchestration.md** (obsoleto)

2. **Criar docs/guides/channels.md** (substituto)
   - Arquitetura real: channels/ com handlers/, backends/, config.py, presets.py
   - ChannelConfig (7 aspectos) com exemplos
   - Presets (pos, remote, marketplace) com pipeline explícito
   - Lifecycle hooks (signal → dispatcher → directives)
   - Como criar um novo canal
   - Como adicionar um handler/modifier/validator customizado

3. **Atualizar docs/reference/signals.md**
   - Listar TODOS os signals conectados (não só 3)
   - order_changed, holds_materialized, production_changed, post_save (directive), post_save (alerts)
   - Signals de payments: payment_authorized, payment_captured, etc.

4. **Atualizar docs/reference/settings.md**
   - Refletir ChannelConfig como mecanismo principal (não settings.CONFIRMATION_FLOW)
   - Documentar cascata: Canal → Shop.defaults → Hardcoded

5. **Atualizar CLAUDE.md**
   - Estrutura do projeto reflete realidade pós-hardening
   - Incluir `shop/` na árvore
   - Remover referências a módulos antigos

6. **Atualizar docs/architecture.md**
   - Diagrama de camadas com shop/ e channels/
   - Fluxo de ChannelConfig cascade

7. **make lint** (verificar links quebrados em docs)

---

## Ordem de Execução

```
WP-B1 (limpeza)           — base limpa, sem resíduos
  │
WP-B2 (config-driven)     — mecanismo de filtragem por canal
  │
WP-B3 (pricing cascade)   — preços corretos end-to-end
  │
  ├── WP-B4 (crafting)    ─┐
  ├── WP-B5 (auth)         ├── independentes entre si
  ├── WP-B6 (fulfillment)  ┘
  │
WP-B7 (documentação)      — reflete tudo que foi feito
```

---

## Prompts de Execução

### WP-B1 — Limpeza de Resíduos
```
Execute WP-B1 do BRIDGE-PLAN.md: Limpeza de Resíduos.

Contexto: O HARDENING-PLAN foi 100% executado. A estrutura atual é:
- shopman-app/shop/ (identidade + regras)
- shopman-app/channels/ (orquestrador: handlers/, backends/, config.py, presets.py)
- shopman-app/channels/web/ (storefront)

Convenções ativas (CLAUDE.md):
- `ref` not `code` — identificadores textuais são `ref`
- Zero backward-compat aliases
- Zero resíduos

Tarefas (fazer na ordem):

1. CHANNEL_CODE → CHANNEL_REF:
   - channels/web/cart.py line 13: renomear constante CHANNEL_CODE → CHANNEL_REF
   - Find-replace global: CHANNEL_CODE → CHANNEL_REF em todos os arquivos

2. Remover aliases backward-compat:
   - channels/web/constants.py: remover HAS_DOORMAN e HAS_STOCKMAN
   - Substituir TODOS os usos por HAS_AUTH e HAS_STOCKING
   - Buscar em todo o codebase: grep -r "HAS_DOORMAN\|HAS_STOCKMAN"

3. Registrar modifiers órfãos:
   - channels/setup.py: adicionar EmployeeDiscountModifier e HappyHourModifier
     na função _register_pricing_modifiers()
   - Importar de shop.modifiers
   - Registrar com register_modifier()

4. Proteger MockPaymentConfirmView:
   - channels/web/views/payment.py: adicionar no início do post():
     if not settings.DEBUG: raise Http404
   - Import: from django.conf import settings; from django.http import Http404

5. Eliminar confirmation_hooks.py:
   - Mover on_payment_confirmed() de confirmation_hooks.py → hooks.py
   - Atualizar import em webhooks.py: from channels.hooks import on_payment_confirmed
   - Deletar confirmation_hooks.py inteiro
   - Verificar que nenhum outro arquivo importa de confirmation_hooks

6. Unificar campo hold TTL:
   - channels/confirmation.py: substituir referências a "checkout_hold_expiration_minutes"
     e "CONFIRMATION_FLOW" por ChannelConfig.effective(channel).stock.hold_ttl_minutes
   - Remover get_hold_expiration() se redundante com ChannelConfig
   - handlers/stock.py: usar ChannelConfig para obter TTL, não dict config antigo

7. Deletar orchestration.md:
   - rm docs/guides/orchestration.md
   - Atualizar docs/README.md removendo a referência

8. make test + make lint — TUDO deve passar

Nota: NÃO criar docs/guides/channels.md ainda (isso é WP-B7).
Apenas limpar resíduos neste WP.
```

### WP-B2 — Modifiers e Validators Config-Driven
```
Execute WP-B2 do BRIDGE-PLAN.md: Modifiers e Validators Config-Driven.

Contexto: ChannelConfig.Rules define listas de modifiers e validators por canal:
  rules=Rules(validators=["business_hours"], modifiers=["employee_discount"])

O mecanismo de FILTRAGEM precisa existir: ModifyService deve rodar APENAS
os modifiers/validators que o canal permite via config.

Leia:
- shopman-core/ordering/shopman/ordering/services/modify.py (ModifyService)
- shopman-core/ordering/shopman/ordering/registry.py (get_modifiers, get_validators)
- shopman-app/channels/config.py (ChannelConfig, Rules)
- shopman-app/channels/setup.py (quais modifiers/validators são registrados)
- shopman-app/shop/modifiers.py (todos os modifiers)

Tarefas:

1. Adicionar atributo `code` a TODOS os modifiers e validators:
   - Pricing: ItemPricingModifier.code = "pricing.item"
   - D1: D1DiscountModifier.code = "d1_discount"
   - Promotion: PromotionModifier.code = "promotion"
   - Coupon: CouponModifier.code = "coupon"
   - Total: SessionTotalModifier.code = "pricing.total"
   - Employee: EmployeeDiscountModifier.code = "employee_discount"
   - HappyHour: HappyHourModifier.code = "happy_hour"
   - Validators: adicionar code se não tiver

2. ModifyService — filtrar modifiers pelo canal:
   - Após obter todos os modifiers do registry (get_modifiers())
   - Ler ChannelConfig.effective(channel).rules.modifiers
   - REGRA: pricing.item e pricing.total SEMPRE rodam (são infraestrutura)
   - Os demais só rodam se listados em rules.modifiers
   - Modifiers que não têm code sempre rodam (backward compat temporário)

3. ModifyService — filtrar validators pelo canal:
   - Mesma lógica: ler rules.validators, filtrar por code

4. Presets — verificar rules nos 3 presets:
   - pos(): validators=["business_hours"], modifiers=["employee_discount"]
   - remote(): validators=["business_hours", "min_order"], modifiers=["happy_hour"]
   - marketplace(): validators=[], modifiers=[]

5. Testes:
   - test_modifier_runs_only_if_in_channel_config
   - test_pricing_modifiers_always_run
   - test_empty_modifiers_list_skips_all_non_infrastructure
   - test_validator_filtered_by_channel_config

6. make test + make lint
```

### WP-B3 — Pricing Cascade Completa
```
Execute WP-B3 do BRIDGE-PLAN.md: Pricing Cascade Completa.

Contexto: O HARDENING-PLAN definiu uma cascata de preços em 3 níveis:
1. Listing do grupo do cliente (se identificado e grupo tem listing_ref)
2. Listing do canal (channel.listing_ref)
3. Preço base do produto (product.base_price_q)

Leia:
- shopman-app/channels/backends/pricing.py (backends existentes)
- shopman-app/channels/setup.py (_register_pricing_modifiers, qual backend é registrado)
- shopman-core/offering/shopman/offering/service.py (CatalogService.unit_price)
- shopman-core/offering/shopman/offering/models/listing.py (ListingItem, min_qty)
- shopman-app/channels/web/views/catalog.py (como catálogo filtra produtos)
- shopman-core/ordering/shopman/ordering/models/channel.py (Channel.listing_ref)
- HARDENING-PLAN.md seções "Pricing cascade" e "Catálogo do canal"

Tarefas:

1. Consolidar pricing backends:
   - Se existe OfferingBackend com cascata E CatalogPricingBackend → consolidar
   - O backend final deve implementar: grupo → canal → base, com suporte a min_qty (tiers)
   - Registrar no setup.py como o backend padrão

2. Catálogo filtrado por listing:
   - catalog.py deve filtrar por channel.listing_ref (dois gates: global + canal)
   - Conforme o padrão descrito no HARDENING-PLAN.md

3. Tiered pricing funcional:
   - Verificar que min_qty em ListingItem é respeitado ao precificar
   - Quantidade maior pode ter preço unitário menor

4. Testes:
   - test_price_from_customer_group_listing
   - test_price_from_channel_listing
   - test_price_fallback_to_base_price
   - test_catalog_filtered_by_channel_listing_ref
   - test_tiered_pricing_respects_min_qty

5. make test + make lint
```

### WP-B4 — Integração Crafting
```
Execute WP-B4 do BRIDGE-PLAN.md: Integração Crafting ↔ App.

Contexto: O Core de Crafting é um micro-MRP com plan(), suggest(), close(), etc.
O App conecta apenas signals básicos. Fechar os loops operacionais.

Leia:
- shopman-core/crafting/shopman/crafting/service.py (CraftService)
- shopman-core/crafting/shopman/crafting/protocols/ (InventoryProtocol, DemandProtocol)
- shopman-core/crafting/shopman/crafting/contrib/demand/ (DemandBackend)
- shopman-app/channels/backends/stock.py (StockingBackend)
- shopman-app/channels/handlers/stock.py (StockHoldHandler, _stock_receivers.py)
- shopman-core/stocking/shopman/stocking/service.py (StockService)
- ADR-007 (docs/decisions/adr-007-crafting-ordering-integration.md)

Tarefas:

1. Verificar adapter Crafting → Stocking:
   - Crafting define InventoryProtocol (consume, receive)
   - O adapter deve conectar a StockService (issue para consumo, receive para produção)
   - Se adapter noop, implementar o real

2. Verificar signal production_changed:
   - Quando WorkOrder fecha → signal production_changed
   - Receiver deve chamar StockService.receive() para produto acabado
   - E StockService.issue() para ingredientes consumidos

3. Sugestão de produção:
   - Criar management command: shop/management/commands/suggest_production.py
   - Usa CraftService.suggest() com demand history
   - Output legível: "Croissant: produzir 50 (demanda média: 45, safety: 10%)"

4. Planned holds → production:
   - Quando availability_policy="planned_ok" e stock=0
   - StockHoldHandler cria hold planejado (target_date)
   - Quando produção se materializa → holds_materialized → auto-commit
   - Verificar este fluxo end-to-end

5. Testes:
   - test_close_work_order_issues_ingredients
   - test_close_work_order_receives_product
   - test_suggest_production_command
   - test_planned_hold_materialized_on_production

6. make test + make lint
```

### WP-B5 — Auth Completo no Storefront
```
Execute WP-B5 do BRIDGE-PLAN.md: Auth Completo no Storefront.

Contexto: O Core de Auth oferece BridgeToken (chat→web), DeviceTrust (skip-OTP),
MagicCode (OTP). O App só usa MagicCode. Completar.

Leia:
- shopman-core/auth/shopman/auth/ (todos os models e services)
- shopman-app/channels/web/views/auth.py (views atuais)
- shopman-app/channels/web/views/account.py (phone-based access)
- shopman-app/channels/web/constants.py (HAS_AUTH)
- shopman-app/channels/web/urls.py (rotas atuais)

Tarefas:

1. BridgeToken — endpoint de consumo:
   - Nova view: BridgeLoginView em auth.py
   - URL: /auth/bridge/<token>/
   - Fluxo: validate token → set session (customer_uuid, verified=True) → redirect
   - Redirect por audience: web_checkout → /checkout, web_account → /conta
   - Token inválido/expirado → página de erro com link para login normal

2. DeviceTrust — skip OTP:
   - Após OTP verificado com sucesso: criar TrustedDevice, setar cookie
   - No login: verificar cookie → se device confiável, auto-login sem OTP
   - Cookie: HttpOnly, Secure, SameSite=Lax, max_age=30 dias
   - Se cookie expirado/inválido: fluxo normal de OTP

3. Session-based auth:
   - Após verificação (OTP ou bridge): setar request.session com:
     customer_uuid, customer_phone, verified=True
   - Account views: verificar session vars, não POST param
   - Middleware ou decorator: @requires_verified_session
   - Expiração: respeitar SESSION_COOKIE_AGE do Django

4. Rate limiting:
   - RequestCodeView: max 3 requests/phone/10min (usar cache)
   - VerifyCodeView: max 5 attempts/phone/10min
   - Retornar 429 com mensagem "Aguarde X minutos"

5. Testes:
   - test_bridge_login_creates_session
   - test_bridge_login_expired_token_fails
   - test_device_trust_skips_otp_on_revisit
   - test_session_auth_protects_account
   - test_rate_limit_on_request_code
   - test_rate_limit_on_verify_code

6. make test + make lint
```

### WP-B6 — Fulfillment, Bundles e Stock Alerts
```
Execute WP-B6 do BRIDGE-PLAN.md: Fulfillment, Bundles e Stock Alerts.

Contexto: Fechar loops operacionais menores que usam capacidades do Core.

Leia:
- shopman-core/offering/shopman/offering/service.py (CatalogService.expand)
- shopman-core/offering/shopman/offering/models/ (ProductComponent)
- shopman-core/stocking/shopman/stocking/models/ (Quant, StockAlert)
- shopman-core/stocking/shopman/stocking/contrib/alerts/
- shopman-core/ordering/shopman/ordering/models/fulfillment.py
- shopman-app/channels/handlers/stock.py (StockHoldHandler)
- shopman-app/channels/handlers/fulfillment.py
- shopman-app/channels/web/views/catalog.py (ProductDetailView)

Tarefas:

1. Bundle expansion no catálogo:
   - ProductDetailView: se product.is_bundle, chamar CatalogService.expand(sku)
   - Passar componentes no contexto: components = [{"sku", "name", "qty"}, ...]
   - Template pode exibir "Contém: 2x Croissant, 1x Baguete, 1x Café"

2. Bundle stock hold:
   - StockHoldHandler: se produto é bundle, explodir em componentes
   - Reservar cada componente individualmente (não o bundle)
   - Usar CatalogService.expand() para obter componentes + qtys
   - Somar qtys se mesmo componente aparece em múltiplos bundles

3. Stock alerts:
   - Verificar se stocking/contrib/alerts/ já tem signal handler
   - Se não, conectar: quando Move cria e Quant._quantity < StockAlert.min_quantity
   - Criar directive NOTIFICATION_SEND com template "stock_alert"
   - Destinatário: operador do canal (configurável) ou fallback para console

4. Fulfillment tracking:
   - Verificar que TrackingView exibe dados do Fulfillment model
   - Verificar auto_sync_fulfillment: fulfillment.dispatched → order.dispatched
   - Verificar tracking URL enrichment funciona

5. Testes:
   - test_product_detail_shows_bundle_components
   - test_bundle_hold_reserves_components
   - test_stock_alert_on_low_quantity
   - test_fulfillment_auto_sync_with_order

6. make test + make lint
```

### WP-B7 — Documentação Atualizada
```
Execute WP-B7 do BRIDGE-PLAN.md: Documentação Atualizada.

Contexto: A documentação precisa refletir o estado real pós-hardening e bridge.
HARDENING-PLAN foi 100% executado. WP-B1 a B6 foram executados.

Leia os arquivos reais (não a documentação) para entender o estado verdadeiro:
- shopman-app/channels/ (toda a estrutura)
- shopman-app/shop/ (toda a estrutura)
- shopman-app/project/settings.py

Tarefas:

1. Criar docs/guides/channels.md (substituto de orchestration.md):
   - Arquitetura: channels/ com config.py, presets.py, handlers/, backends/, hooks.py, setup.py
   - ChannelConfig: 7 aspectos, cada um com exemplos concretos
   - Presets: pos(), remote(), marketplace() com pipeline completo
   - Lifecycle: signal → hooks.py → directives → handlers
   - Como criar um novo canal (com exemplo)
   - Como adicionar handler/modifier/validator customizado (com exemplo)
   - Cascata: Canal → Shop.defaults → Hardcoded

2. Atualizar docs/reference/signals.md:
   - Listar TODOS os signals conectados na app
   - Incluir signals de payments, customers, auth
   - Marcar quais são ativamente conectados

3. Atualizar docs/reference/settings.md:
   - ChannelConfig como mecanismo principal (não settings.CONFIRMATION_FLOW)
   - Cascata documentada

4. Atualizar CLAUDE.md:
   - Árvore de projeto atualizada com shop/ e channels/
   - Remover referências a módulos antigos

5. Atualizar docs/architecture.md:
   - Diagrama reflete shop/ + channels/ (não os mini-apps antigos)

6. Atualizar docs/README.md:
   - Índice correto (channels.md em vez de orchestration.md)

7. make lint
```

---

## Critério de Aceite Global

1. `make test` — 100% (0 failures)
2. `make lint` — 0 warnings
3. App utiliza TODAS as capacidades do Core: Crafting (suggest, plan, close),
   Auth (BridgeToken, DeviceTrust), Bundles (expand), Stock Alerts, Fulfillment completo
4. Modifiers/Validators filtrados por canal via config
5. Pricing cascade funcional: grupo → canal → base
6. Documentação reflete a realidade
7. Zero resíduos de iterações anteriores
8. Zero aliases backward-compat

---

## Protocolo de Execução

Ao concluir um WP:
1. Rodar `make test` + `make lint`
2. Reportar resultado
3. Mostrar o prompt completo do PRÓXIMO WP
4. Se último WP: "Bridge completo. Core e App alinhados."

Sequência: B1 → B2 → B3 → B4/B5/B6 (paralelos) → B7
