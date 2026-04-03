# WP-R8: Testes + Cleanup — Prompt de Sessão

Estou executando o WP-R8 do plano RESTRUCTURE-APP-PLAN.md (na raiz do repo). Leia o plano INTEIRO antes de começar — ele contém contexto arquitetural essencial (princípios, consistência semântica, hierarquia de flows, apps.py wiring).

Objetivo: Eliminar dependências de `channels/` e `shop/` no `shopman/`, migrar views e utilitários faltantes, migrar testes, e remover código antigo.

Contexto: R0–R7 estão prontos. O shopman/ funciona via bridge migration: web views re-exportam de channels/, webhooks já foram migrados, checkout e cancel usam services. Agora precisamos cortar o cordão umbilical.

## Estado Atual (R7 concluído)

### shopman/ importa de channels/ nestes pontos:

1. `shopman/apps.py:55` — `from channels.setup import register_all` (registra handlers no ordering registry)
2. `shopman/web/views/__init__.py` — re-export wildcard de `channels.web.views`
3. `shopman/web/views/checkout.py` — importa `CheckoutDefaultsService`, `ChannelConfig`, `CartService`, `CHANNEL_REF`, `get_default_ddd`, `CepLookupView`, `OrderConfirmationView`
4. `shopman/web/views/tracking.py` — importa `OrderStatusPartialView`, `OrderTrackingView`, `ReorderView`, `_build_tracking_context`, `_CANCELLABLE_STATUSES`
5. `shopman/web/urls.py` — importa `ManifestView`, `OfflineView`, `ServiceWorkerView` de channels/web/views/pwa
6. `shopman/api/urls.py` — importa `urlpatterns` de channels.api.urls
7. `shopman/templatetags/storefront_tags.py` — re-export de channels.web.templatetags
8. `shopman/webhooks/efi.py:142` — `from channels.config import ChannelConfig` (auto_transition)
9. `shopman/webhooks/stripe.py:60,122` — `from channels.backends.payment_stripe import StripeBackend` + `ChannelConfig`

### shopman/ importa de shop/ nestes pontos:

1. `shopman/admin/shop.py:35-36` — `from shop.views.closing import closing_view` + `from shop.views.production import production_view, production_void_view`

### channels/ importa de shop/ nestes pontos (afeta views re-exportadas):

- channels/web/views/*.py — ~20 ocorrências de `from shop.models import Shop, Promotion, KDSInstance, KDSTicket, Coupon`
- channels/web/views/__init__.py — `from shop.views.pos import ...` + `from shop.views.production import ...`
- channels/web/views/_helpers.py — `from shop.modifiers import D1_DISCOUNT_PERCENT` + `from shop.models import Shop`
- channels/web/cart.py — `from shop.models import Coupon`
- channels/web/constants.py — `from shop.models import Shop`
- channels/config.py — `from shop.models import Shop`
- channels/hooks.py — `from shop.models import OperatorAlert`

### Testes atuais:

- `shopman/tests/` — 206 testes passando (test_services, test_flows, test_adapters, test_rules, test_admin, test_web)
- `tests/` (fora do shopman) — 164 passando + 13 skipped (web, integration, e2e, phone)
- `tests/web/` — testes de checkout, catalog, auth, account, devices, pwa
- `tests/integration/` — crafting↔offering, crafting↔stocking, ordering↔auth, customers↔auth
- `tests/e2e/` — storefront e2e

### Arquivos a remover:

- `channels/` inteiro — 84 .py files, ~14.619 LOC (handlers, backends, config, presets, hooks, topics, setup, web views, api, webhooks, cart, templates, static, templatetags)
- `shop/` inteiro — 39 .py files, ~5.275 LOC (models, admin, views, modifiers, validators, dashboard, widgets, migrations, templates, management)

### O que já existe em shopman/ (NÃO precisa recriar):

- `shopman/models/` — Shop, NotificationTemplate, Promotion, Coupon, RuleConfig, OperatorAlert, KDSInstance, KDSTicket, DayClosing
- `shopman/services/` — stock, payment, customer, notification, fulfillment, loyalty, fiscal, pricing, cancellation, kds, checkout (11 services)
- `shopman/adapters/` — payment_efi, payment_stripe, payment_mock, notification_manychat, notification_email, notification_console, stock_internal, otp_manychat
- `shopman/rules/` — engine, pricing, validation
- `shopman/admin/` — shop, orders, alerts, kds, closing, rules, dashboard, widgets
- `shopman/flows.py` — BaseFlow, LocalFlow, RemoteFlow, MarketplaceFlow + subflows
- `shopman/webhooks/` — efi, stripe (já migrados, usam flows.dispatch)

## Entregáveis

### Fase 1: Migrar código que ainda vive em channels/ e shop/

#### 1.1 Web views — copiar para shopman/web/views/ (substituir bridge)

Copiar TODOS os módulos de `channels/web/views/` para `shopman/web/views/`:
- `_helpers.py`, `account.py`, `auth.py`, `bridge.py`, `cart.py`, `catalog.py`, `devices.py`, `home.py`, `info.py`, `kds.py`, `payment.py`, `pedidos.py`, `pwa.py`
- `checkout.py` e `tracking.py` já existem em shopman/ (refatorados em R7) — NÃO sobrescrever
- Em TODOS os arquivos copiados: substituir `from shop.models import ...` por `from shopman.models import ...`
- Em TODOS: substituir `from shop.modifiers import ...` por equivalente em shopman/rules/ ou inline

Atualizar `shopman/web/views/__init__.py` para importar dos módulos LOCAIS (não mais de channels/).

#### 1.2 Cart service — copiar channels/web/cart.py para shopman/web/cart.py

- Substituir `from shop.models import Coupon` por `from shopman.models import Coupon`
- Atualizar imports em checkout.py e _helpers.py

#### 1.3 Constants e helpers — copiar channels/web/constants.py

- Substituir `from shop.models import Shop` por `from shopman.models import Shop`

#### 1.4 Context processors — migrar channels/web/context_processors.py

- Copiar para shopman/web/context_processors.py
- Atualizar import de CartService
- Atualizar settings.py: `"channels.web.context_processors.cart_count"` → `"shopman.web.context_processors.cart_count"`

#### 1.5 Templatetags — copiar channels/web/templatetags/storefront_tags.py

- Copiar para shopman/templatetags/storefront_tags.py (substituir o bridge)
- Substituir qualquer import de shop/channels

#### 1.6 Templates — mover channels/web/templates/ para shopman/templates/

- Mover (ou copiar) os 79 template files de `channels/web/templates/` para `shopman/templates/`
- Remover o `channels/web/templates` do TEMPLATE_DIRS no settings.py (não precisa mais — APP_DIRS encontra)
- Corrigir qualquer referência a `{% url 'admin:shop_closing' %}` no template do dashboard (se existir)

#### 1.7 Static files — mover channels/web/static/ para shopman/static/

#### 1.8 API views — copiar channels/api/ para shopman/api/

- Copiar views.py, serializers.py, catalog.py, account.py, tracking.py
- Substituir imports de channels/web/cart e _helpers
- Atualizar shopman/api/urls.py para importar dos módulos locais

#### 1.9 POS views — copiar shop/views/pos.py para shopman/web/views/pos.py

- Substituir imports de shop.models
- Atualizar __init__.py e urls.py

#### 1.10 Production/Closing views — copiar shop/views/production.py e closing.py para shopman/web/views/

- Substituir imports de shop.models → shopman.models
- Atualizar admin/shop.py: `from shop.views.closing import ...` → `from shopman.web.views.closing import ...`
- Atualizar admin/shop.py: `from shop.views.production import ...` → `from shopman.web.views.production import ...`

#### 1.11 ChannelConfig — avaliar dependência

`channels/config.py` define `ChannelConfig` (dataclass que lê `Channel.config`). É usada por:
- checkout.py (payment methods, cutoff info)
- tracking.py (confirmation mode, timeout)
- webhooks/efi.py e stripe.py (auto_transition)

Opções:
- **A) Copiar ChannelConfig para shopman/** — se for simples
- **B) Ler Channel.config diretamente** — eliminar a abstração (o config já é um dict no Channel model)
- Escolher a opção mais pragmática. Se ChannelConfig for pequeno e autocontido, copiar. Se tiver muitas dependências, ler config direto.

#### 1.12 channels/setup.py → shopman/apps.py

O `register_all()` de `channels/setup.py` registra handlers no ordering registry. O apps.py chama isso.
- Copiar a lógica de registro para dentro de apps.py ou para um `shopman/setup.py`
- Atualizar imports: handlers de `channels/handlers/` → precisam ser copiados OU a lógica substituída
- NOTA: Muitos handlers são wrappers finos que já foram substituídos por flows/services. Avaliar quais handlers AINDA são necessários (stock signals, check handlers) vs quais são dead code agora que flows.py existe.

### Fase 2: Testes

#### 2.1 Migrar testes de tests/ para shopman/tests/

- `tests/web/` → `shopman/tests/web/` (test_web_checkout, test_web_catalog, test_web_auth, test_web_account, test_web_devices, test_web_pwa, conftest)
- `tests/integration/` → `shopman/tests/integration/`
- `tests/e2e/` → `shopman/tests/e2e/`
- `tests/test_phone_normalization.py` → `shopman/tests/`
- `tests/test_webhook.py` → `shopman/tests/`
- Atualizar imports onde necessário

#### 2.2 Novos testes (se faltantes):

- `test_cancellation.py` — 4 paths convergem para 1 service (customer, operator, confirmation timeout, payment timeout)
- `test_race_conditions.py` — payment after cancel, concurrent operations
- Testes de integração: flow completo web (cart → checkout → payment → tracking)

### Fase 3: Cleanup

#### 3.1 Remover channels/ inteiro

```
rm -rf shopman-app/channels/
```

#### 3.2 Remover shop/ inteiro

```
rm -rf shopman-app/shop/
```

#### 3.3 Limpar settings.py

- Remover `channels/web/templates` de TEMPLATE_DIRS (se ainda presente)
- Verificar que não há referências a channels ou shop em INSTALLED_APPS, MIDDLEWARE, etc.

#### 3.4 Limpar project/urls.py

- Verificar que não há referências a channels ou shop

#### 3.5 Verificar zero imports residuais

```bash
grep -rn "from channels\.\|from shop\.\|import channels\.\|import shop\." shopman-app/shopman/ --include="*.py"
```

Deve retornar ZERO resultados.

#### 3.6 Limpar arquivos de git status

- Os arquivos deletados em git status (test files antigos) podem ser commited
- Os arquivos ?? (novos) já estão tracked

## O que NÃO fazer

- NÃO alterar o Core — tudo fica no app layer
- NÃO inventar features — migrar e limpar, nada mais
- NÃO remover funcionalidade — tudo que channels/ e shop/ faziam deve funcionar via shopman/
- NÃO duplicar admin registration — verificar que models não ficam registrados 2x
- NÃO quebrar URLs — todos os URL names (`storefront:*`, `api-*`, `webhooks:*`) devem continuar funcionando

## Critério de Sucesso

1. `make lint` limpo
2. TODOS os testes passam (206+ shopman + 164+ app-level)
3. `grep -rn "from channels\.\|from shop\." shopman-app/shopman/ --include="*.py"` retorna ZERO
4. `ls shopman-app/channels/ shopman-app/shop/` retorna "No such file or directory"
5. `make run` funciona — storefront acessível
6. URLs resolvem: home, checkout, cart, payment, tracking, cancel, api, webhooks
7. Dashboard admin funcional com KPIs
8. Operador consegue: ver/editar Shop, reconhecer alertas, ver KDS, ver directives, ver dashboard

## Ordem sugerida

1. Fase 1 em batch: copiar views, cart, constants, context_processors, templatetags, templates, static, API, POS, production/closing
2. Fase 1 ChannelConfig: decidir e executar
3. Fase 1 setup.py/handlers: avaliar e migrar
4. Atualizar todos os imports em shopman/ para apontar para módulos locais
5. Rodar testes — garantir que tudo passa SEM channels/ e shop/
6. Fase 2: migrar testes
7. Fase 3: rm -rf channels/ e shop/
8. Rodar testes finais + lint

Já fica previamente aprovado para fazer todas as alterações pertinentes à tarefa. Vou me ausentar e quando retornar quero o trabalho concluido!
