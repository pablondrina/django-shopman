# ARCH-PLAN — Simplificação Arquitetural

## Contexto

Análise em 3 rodadas (análise → autocrítica → tréplica) identificou que a
arquitetura do Shopman está conceitualmente correta (3 camadas: Core, Framework,
Instância) mas com excesso de abstrações e camadas misturadas.

**Diagnóstico final:**
- 10 conceitos arquiteturais na App layer, ~3 são redundantes ou dead code
- Backends e adapters fazem a mesma coisa com nomes/mecanismos diferentes
- Rules engine e Modifiers: dois mecanismos para a mesma preocupação
- Pipeline em ChannelConfig: dead code (definido, nunca consumido)
- setup.py: registro imperativo que deveria ser declarativo via settings
- Camada 1 (framework genérico) e Camada 2 (instância) misturadas no mesmo diretório

**Resultado esperado: 6 conceitos claros**
1. Channel (config + cascata)
2. Flow (classes, herança, registry)
3. Services (cola order↔core)
4. Core Services (chamados diretamente, sem wrapper)
5. Directives + Handlers (async queue)
6. Adapters (integrações externas — unificado, um só mecanismo)

## Decisões de Naming

### Core Apps (Layer 0) — nomes de persona

| Persona | Pip package | Python namespace | Domínio | Admin verbose_name |
|---|---|---|---|---|
| Omniman | `shopman-omniman` | `shopman.omniman` | Pedidos omnichannel | "Pedidos" |
| Stockman | `shopman-stockman` | `shopman.stockman` | Estoque | "Estoque" |
| Craftsman | `shopman-craftsman` | `shopman.craftsman` | Produção | "Produção" |
| Offerman | `shopman-offerman` | `shopman.offerman` | Catálogo | "Catálogo" |
| Guestman | `shopman-guestman` | `shopman.guestman` | CRM | "Clientes" |
| Doorman | `shopman-doorman` | `shopman.doorman` | Auth | "Autenticação" |
| Payman | `shopman-payman` | `shopman.payman` | Pagamentos | "Pagamentos" |

**Utils** permanece como `shopman-utils` / `shopman.utils` — é fundação
cross-app que vive na Layer 0 (core packages dependem dele; se morasse
no framework, criaria dependência circular).

### Convenção de visibilidade

- **Nomes de persona** = código (imports, packages, pip, docs técnicos)
- **verbose_name** = usuário final (admin sidebar, breadcrumbs, títulos)
- Instância pode sobrescrever verbose_name via AppConfig customizado

Exemplo:
```python
# core/omniman/shopman/omniman/apps.py
class OmnimanConfig(AppConfig):
    name = "shopman.omniman"
    verbose_name = "Pedidos"  # usuário vê isso no admin
```

## Relação com DEBT-PLAN

DEBT-PLAN (D1-D4) permanece inalterado. **Executar DEBT-PLAN ANTES de ARCH-PLAN.**

- D1 (stock fulfill retry) — bugfix no handler, válido no código atual
- D2 (checkout duplication) — independente
- D3 (N+1 queries) — independente
- D4 (view logging) — independente

Após DEBT-PLAN concluído, executar ARCH-PLAN na ordem: A1 → A2 → A3 → A4 → A5.

---

## WP-A1: Deletar Pipeline Dead Code + Cleanup Inicial

**Status:** concluído
**Risco:** zero (remove código que nada consome)
**Escopo:** config.py + backward compat alias em protocols.py

### Prompt

```
Execute o WP-A1 do ARCH-PLAN.md.

## Contexto

O `ChannelConfig` em `shopman-app/shopman/config.py` define um dataclass
`Pipeline` com 10 listas de topics (on_commit, on_confirmed, etc.). Este
Pipeline é parseado no `from_dict()` mas **nunca consumido em lugar nenhum
do codebase**. Flows (`flows.py`) chamam services diretamente — Pipeline
foi o mecanismo original de orquestração, substituído por Flows, mas nunca
removido.

Verificar ANTES de alterar: confirmar que nenhum código lê
`config.pipeline` ou qualquer variante. Grep por:
- `\.pipeline\.` ou `\.pipeline[` em todo o projeto
- `config\.pipeline` em todo o projeto
- `Pipeline` em arquivos que NÃO sejam config.py

Se encontrar consumidores reais, PARAR e reportar.

Também existe um backward-compat alias em `protocols.py`:
```python
from shopman.payman.protocols import (
    GatewayIntent as PaymentIntent,  # Backward compat alias
)
```
Projeto novo, sem consumidores externos — aliases não devem existir
(convenção: zero backward-compat).

## Alteração 1: shopman-app/shopman/config.py

1. Remover a classe `Pipeline` inteira (dataclass com 10 fields)
2. Remover o campo `pipeline: Pipeline = field(default_factory=Pipeline)`
   do ChannelConfig
3. Remover a linha de parsing de pipeline em `from_dict()`:
   ```python
   pipeline=_safe_init(
       cls.Pipeline,
       {k: v for k, v in data.get("pipeline", {}).items() if k.startswith("on_")},
   ),
   ```
4. Remover o import/referência de Pipeline no `__all__` se existir
5. Remover menção a Pipeline no docstring do ChannelConfig

## Alteração 2: shopman-app/shopman/protocols.py

1. Remover o alias:
   ```python
   from shopman.payman.protocols import (
       GatewayIntent as PaymentIntent,  # Backward compat alias
   )
   ```
2. Remover `PaymentIntent` do `__all__`
3. Grep por `PaymentIntent` em todo o projeto — se houver usos, substituir
   por `GatewayIntent` (o nome real)

## Alteração 3: Qualquer teste ou fixture

Se algum teste cria ChannelConfig com pipeline, remover esse campo do
teste. Não deve haver, mas verificar.

## Verificação
- `make test` (todos — garantir que nada quebrou)
- `make lint`
- Grep final: `Pipeline` não deve aparecer em config.py
- Grep final: `PaymentIntent` não deve aparecer fora de __all__ removal
```

---

## WP-A2: Unificar Adapters e Backends

**Status:** concluído
**Risco:** médio (reorganiza indireção, mas sem mudar comportamento)
**Escopo:** backends/, adapters/, handlers/, setup.py, protocols.py

### Prompt

```
Execute o WP-A2 do ARCH-PLAN.md.

## Contexto

O projeto tem DOIS mecanismos para abstrair implementações:

1. **adapters/** — resolvidos dinamicamente via `get_adapter(type, method)`
   em `shopman-app/shopman/adapters/__init__.py`. Usados por services
   (payment.initiate → get_adapter("payment", method="pix")).

2. **backends/** — instanciados em `setup.py` e injetados nos handlers
   no boot. Handlers recebem `backend` no construtor.

Ambos implementam protocols de `protocols.py`. A separação cria confusão:
existem arquivos duplicados (ex: payment_efi em AMBOS os diretórios).

A unificação segue o princípio: **uma coisa, um nome, um mecanismo.**

## Passo 1: Entender o estado atual

ANTES de qualquer alteração, fazer inventário:

1. Ler `shopman-app/shopman/adapters/__init__.py` — entender get_adapter()
2. Listar TODOS os arquivos em `adapters/` e `backends/`
3. Para cada par duplicado (ex: payment_efi em ambos), ler ambos e
   entender qual faz o quê
4. Ler `setup.py` — entender como backends são instanciados e injetados
5. Ler os handlers que recebem backends no construtor:
   - handlers/stock.py (StockHoldHandler, StockCommitHandler)
   - handlers/payment.py
   - handlers/notification.py
   - Outros que recebam backend

## Passo 2: Classificar cada backend

Para cada arquivo em backends/, classificar:

**Tipo A — Wrapper de Core service (absorver no handler):**
- `backends/stock.py` (StockingBackend) — wraps shopman.stockman.service.Stock
  → A lógica deve migrar para os handlers que a consomem

**Tipo B — Implementação de integração externa (mover para adapters/):**
- `backends/payment_*.py` — se duplica adapter, consolidar
- `backends/notification_*.py` — se duplica adapter, consolidar
- `backends/fiscal_*.py` — mover para adapters/
- `backends/accounting_*.py` — mover para adapters/

**Tipo C — Lógica de framework (manter inline ou em services/):**
- `backends/pricing.py` — avaliar se é adapter ou lógica inline
- `backends/customer.py` — avaliar se é adapter ou lógica inline
- `backends/cost.py` — avaliar
- `backends/checkout_defaults.py` — avaliar

## Passo 3: Absorver stock backend nos handlers

Este é o caso mais claro e importante.

`StockHoldHandler` e `StockCommitHandler` em `handlers/stock.py` recebem
`backend: StockBackend` e chamam métodos como:
- `self.backend.check_availability(sku, qty, ...)`
- `self.backend.create_hold(sku, qty, ...)`
- `self.backend.fulfill_hold(hold_id, ...)`
- `self.backend.release_hold(hold_id)`
- `self.backend.release_holds_for_reference(ref)`

Esses métodos em `backends/stock.py` são wrappers que chamam
`shopman.stockman.service.Stock.*()` com tratamento de exceção.

**Ação:**
1. Em cada handler, substituir `self.backend.X()` por chamada direta a
   `shopman.stockman.service.Stock.X()` (com o mesmo tratamento de
   exceção que o backend fazia)
2. Mover a lógica de status validation de `fulfill_hold()` para dentro
   do StockCommitHandler.handle()
3. Remover a injeção de `backend` no construtor dos handlers
4. Remover `backends/stock.py`
5. Atualizar `setup.py` para não instanciar StockingBackend

**Cuidado:** manter a idempotência que `fulfill_hold()` implementa
(check FULFILLED → return). E manter o `_stocking_available()` guard
(o handler deve verificar se stocking está instalado).

## Passo 4: Consolidar backends de integração com adapters

Para cada backend Tipo B:
1. Se existe duplicata em adapters/, ler ambos e mesclar no adapter
   (mantendo a interface de get_adapter)
2. Se NÃO existe duplicata, mover o arquivo para adapters/
3. Atualizar `setup.py` e qualquer handler que referenciava o backend
4. Atualizar `get_adapter()` defaults se necessário

## Passo 5: Resolver backends Tipo C

Para cada backend que é lógica de framework:
1. Se é pequeno e usado por UM handler → inline no handler
2. Se é reutilizado → mover para services/
3. Documentar a decisão em comentário

## Passo 6: Remover diretório backends/

Após todos os backends terem sido absorvidos, movidos, ou inlineados:
1. Remover `shopman-app/shopman/backends/` inteiro
2. Atualizar imports em todo o projeto
3. Limpar `StockBackend` protocol de `protocols.py` se não for mais
   necessário (handlers chamam Core diretamente)

## Passo 7: Atualizar setup.py

Remover toda instanciação de backends. Handlers que antes recebiam
backends agora são autônomos. A registration de handlers em setup.py
continua (será simplificada no WP-A3).

## Verificação
- `make test` (todos)
- `make lint`
- Grep: `from shopman.backends` não deve aparecer em nenhum lugar
- Grep: `backends/` directory não deve existir
- Confirmar que `get_adapter()` continua funcionando para payment,
  notification, etc.
```

---

## WP-A3: Registro via Settings + Consolidação Rules/Modifiers

**Status:** concluído
**Risco:** médio (muda boot sequence, mas sem mudar comportamento)
**Escopo:** setup.py, apps.py, settings.py, rules/, modifiers.py

### Prompt

```
Execute o WP-A3 do ARCH-PLAN.md.

## Contexto

Dois problemas relacionados:

### Problema 1: setup.py imperativo

`setup.py` tem `register_all()` com 16 funções `_register_*()` chamadas
no boot. Cada uma importa handlers/modifiers e chama
`registry.register_directive_handler()` / `register_modifier()` etc.

O padrão Djangônico (DRF, Salesman) é declarar em settings como dotted
paths, resolver lazy no boot. Mais explícito, mais configurável.

### Problema 2: Rules + Modifiers duplicados

Dois mecanismos coexistem:
- Modifiers registrados via `setup.py` → `registry.register_modifier()`
  (rodam sempre)
- Rules via `rules/engine.py` + `RuleConfig` no DB (configuráveis via admin,
  mas SÓ para validators — modifiers ignoram o engine)

O próprio código reconhece isso em `rules/engine.py:67-69`:
"For R5, only registers VALIDATORS... R8 will migrate everything."

## Passo 1: Entender o estado atual

1. Ler `shopman-app/shopman/setup.py` completo
2. Ler `shopman-app/shopman/rules/engine.py` completo
3. Ler `shopman-app/shopman/rules/pricing.py` e `validation.py`
4. Ler `shopman-app/shopman/apps.py`
5. Ler `shopman-app/project/settings.py` — buscar SHOPMAN_* settings
6. Listar TODOS os handlers, modifiers, validators registrados

## Passo 2: Criar settings declarativas

Em `project/settings.py`, adicionar:

```python
# ── Shopman Component Registration ──

SHOPMAN_HANDLERS = [
    "shopman.handlers.stock.StockHoldHandler",
    "shopman.handlers.stock.StockCommitHandler",
    "shopman.handlers.payment.PaymentCaptureHandler",
    "shopman.handlers.payment.PaymentRefundHandler",
    "shopman.handlers.payment.PixGenerateHandler",
    "shopman.handlers.payment.PixTimeoutHandler",
    "shopman.handlers.payment.PaymentTimeoutHandler",
    "shopman.handlers.payment.CardCreateHandler",
    "shopman.handlers.notification.NotificationSendHandler",
    "shopman.handlers.confirmation.ConfirmationTimeoutHandler",
    "shopman.handlers.customer.CustomerEnsureHandler",
    "shopman.handlers.fiscal.FiscalEmitHandler",
    "shopman.handlers.fiscal.FiscalCancelHandler",
    "shopman.handlers.accounting.AccountingHandler",
    "shopman.handlers.returns.ReturnHandler",
    "shopman.handlers.fulfillment.FulfillmentHandler",
    "shopman.handlers.loyalty.LoyaltyHandler",
    "shopman.handlers.checkout_defaults.CheckoutDefaultsHandler",
]

SHOPMAN_MODIFIERS = [
    "shopman.handlers.pricing.ItemPricingModifier",
    "shopman.modifiers.D1DiscountModifier",
    "shopman.modifiers.DiscountModifier",
    "shopman.modifiers.EmployeeDiscountModifier",
    "shopman.modifiers.HappyHourModifier",
]

SHOPMAN_VALIDATORS = [
    "shopman.handlers.stock.StockCheckValidator",
]

SHOPMAN_CHECKS = [
    "shopman.handlers.stock.StockCheck",
]
```

NOTA: os nomes/paths acima são aproximados — ler o `setup.py` atual
para pegar os nomes exatos das classes e seus módulos.

## Passo 3: Reescrever apps.py para ler settings

Substituir `_register_handlers()` em apps.py por:

```python
def _register_components(self):
    """Register handlers, modifiers, validators, checks from settings."""
    from django.conf import settings
    from shopman.omniman import registry

    for dotted in getattr(settings, "SHOPMAN_HANDLERS", []):
        cls = self._import(dotted)
        if cls:
            try:
                registry.register_directive_handler(cls())
            except (ValueError, TypeError):
                logger.warning("Already registered or invalid: %s", dotted)

    for dotted in getattr(settings, "SHOPMAN_MODIFIERS", []):
        cls = self._import(dotted)
        if cls:
            try:
                registry.register_modifier(cls())
            except (ValueError, TypeError):
                logger.warning("Already registered or invalid: %s", dotted)

    # Similar para validators e checks

def _import(self, dotted_path):
    """Import class from dotted path."""
    try:
        module_path, class_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError):
        logger.warning("Could not import: %s", dotted_path)
        return None
```

NOTA: adaptar conforme necessário — alguns handlers podem precisar de
argumentos no construtor (verificar no setup.py atual). Se precisarem,
o handler deve resolver suas próprias dependências internamente (não
receber via construtor, como já será o caso após WP-A2).

## Passo 4: Consolidar Rules + Modifiers

1. Remover `rules/pricing.py` — as classes de rule wrapper que existem
   lá (D1Rule, PromotionRule, etc.) são wrappers dos modifiers que já
   estão em `modifiers.py`. Duplicação.

2. Manter `rules/engine.py` SIMPLIFICADO:
   - `get_active_rules()` retorna RuleConfigs ativas
   - RuleConfig no admin serve para ATIVAR/DESATIVAR modifiers e validators
   - O campo `rule_path` aponta para o modifier/validator real
   - `invalidate_rules_cache()` continua funcionando

3. Manter `rules/validation.py` — BusinessHoursRule e MinimumOrderRule
   são validators reais, não wrappers

4. Em apps.py, após registrar modifiers/validators de SHOPMAN_MODIFIERS
   e SHOPMAN_VALIDATORS, consultar RuleConfig para desativar os que
   estão disabled no admin:
   ```python
   # Pseudo-code:
   active_rules = RuleConfig.objects.filter(enabled=True)
   # Desregistrar modifiers cujo rule_path não está em active_rules
   ```

   Ou, mais simples: modifiers checam internamente se estão ativos:
   ```python
   class D1DiscountModifier:
       def modify(self, item, context):
           if not self._is_active(context.get("channel")):
               return
           # ... lógica real
   ```

5. Escolher a abordagem mais simples. Se a verificação interna for
   mais limpa que desregistrar/re-registrar, usar essa.

## Passo 5: Deletar setup.py

Após toda a lógica de registro estar em apps.py (lendo settings):
1. Deletar `shopman-app/shopman/setup.py` completamente
2. Remover `from shopman.setup import register_all` em apps.py
3. A função `_register_stock_signals()` que existia em setup.py
   precisa migrar — provavelmente para apps.py diretamente, como
   `_connect_stock_signals()` (similar a `_connect_flow_signal()`)

## Verificação
- `make test` (todos)
- `make lint`
- Grep: `setup.py` não deve existir
- Grep: `register_all` não deve aparecer
- Confirmar que todos handlers/modifiers/validators continuam
  funcionando (testes de flow, testes de pricing, etc.)
- Confirmar que RuleConfig no admin ativa/desativa modifiers
```

---

## WP-A4: Reorganização de Pastas — Separar Framework e Instância

**Status:** concluído
**Risco:** alto (move muitos arquivos, mas sem mudar lógica)
**Escopo:** toda a estrutura de diretórios
**Pré-requisito:** WP-A1, WP-A2, WP-A3 concluídos + DEBT-PLAN concluído

### Prompt

```
Execute o WP-A4 do ARCH-PLAN.md.

## Contexto

Após WP-A1/A2/A3, o código está limpo:
- Sem Pipeline dead code
- Sem diretório backends/ (absorvido)
- Registro via settings (sem setup.py)
- Rules/Modifiers consolidados

Agora vamos reorganizar para separar Framework (Layer 1) de Instância
(Layer 2), preparando para pip-installability futura.

## Estrutura Alvo

A partir do diretório de trabalho (hoje `shopman-app/`), a estrutura
alvo é:

```
shopman/                    # Framework (Layer 1) — Django app
├── __init__.py
├── apps.py                 # Boot: lê settings, registra componentes
├── flows.py                # BaseFlow, LocalFlow, RemoteFlow, MarketplaceFlow
├── config.py               # ChannelConfig + cascata (sem Pipeline)
├── protocols.py            # Protocols restantes (adapter contracts)
├── topics.py               # Topic constants
├── notifications.py        # Notification registry + dispatch
├── confirmation.py         # Confirmation helpers
├── middleware.py            # ChannelParamMiddleware, OnboardingMiddleware
├── context_processors.py   # shop(), cart_count()
├── services/               # Orquestração order↔core
│   ├── stock.py
│   ├── payment.py
│   ├── customer.py
│   ├── notification.py
│   ├── checkout.py
│   ├── checkout_defaults.py
│   ├── fulfillment.py
│   ├── kds.py
│   ├── pricing.py
│   ├── cancellation.py
│   ├── production.py
│   ├── fiscal.py
│   └── loyalty.py
├── handlers/               # Directive handlers
│   ├── stock.py
│   ├── payment.py
│   ├── notification.py
│   ├── confirmation.py
│   ├── customer.py
│   ├── fiscal.py
│   ├── accounting.py
│   ├── returns.py
│   ├── fulfillment.py
│   ├── loyalty.py
│   ├── checkout_defaults.py
│   ├── pricing.py
│   ├── kds_dispatch.py
│   └── stock_alerts.py
├── adapters/               # Adapter framework + implementações genéricas
│   ├── __init__.py         # get_adapter()
│   ├── payment_mock.py     # Mock (testing)
│   ├── notification_console.py  # Console (dev)
│   ├── notification_email.py    # Email (genérico)
│   ├── notification_sms.py      # SMS (genérico)
│   └── stock_internal.py   # Internal stocking (se ainda necessário)
├── models/                 # Framework models
│   ├── shop.py             # Shop
│   ├── rules.py            # RuleConfig
│   ├── alerts.py           # OperatorAlert
│   ├── kds.py              # KDSInstance, KDSTicket
│   └── closing.py          # DayClosing
├── rules/                  # Rules engine (simplificado)
│   ├── engine.py           # Loader + cache
│   └── validation.py       # BusinessHoursRule, MinimumOrderRule
├── admin/                  # Admin configs
├── api/                    # REST API base
├── web/                    # Storefront base (views + templates overridáveis)
│   ├── views/
│   ├── cart.py
│   ├── constants.py
│   ├── urls.py
│   └── templates/
├── templatetags/
├── production_flows.py
├── kds_utils.py
├── modifiers.py            # PromotionModifier, DiscountModifier (genéricos)
├── management/
│   └── commands/
│       ├── cleanup_d1.py
│       ├── cleanup_stale_sessions.py
│       └── suggest_production.py
└── migrations/

nelson/                     # Instância (Layer 2) — Nelson Boulangerie
├── __init__.py
├── apps.py                 # NelsonConfig
├── flows.py                # ManychatFlow, IFoodFlow, PosFlow, TotemFlow,
│                           #   WhatsAppFlow, WebFlow (estendem base flows)
├── adapters/               # Gateways específicos
│   ├── payment_efi.py      # EFI PIX
│   ├── payment_stripe.py   # Stripe
│   ├── notification_manychat.py  # ManyChat
│   ├── otp_manychat.py     # OTP via ManyChat
│   ├── fiscal_focus.py     # Focus NFC-e
│   ├── fiscal_mock.py      # Mock fiscal
│   └── accounting_contaazul.py   # ContaAzul
├── modifiers.py            # D1Discount, HappyHour, EmployeeDiscount
├── webhooks/               # Webhooks de gateways específicos
│   ├── urls.py
│   ├── efi.py
│   └── stripe.py
├── web/                    # Views e templates específicos (override)
│   ├── views/              # Views adicionais ou overrides
│   └── templates/          # Template overrides
└── management/
    └── commands/
        └── seed.py         # Dados Nelson Boulangerie

project/                    # Django project config
├── settings.py             # INSTALLED_APPS, SHOPMAN_*, adapter config
├── urls.py
└── wsgi.py
```

NOTA: a instância se chama `nelson/` (não `instance/`). Quando virar
cookiecutter, o nome será `{{project_name}}/`.

## Passo 1: Entender dependências

ANTES de mover qualquer arquivo:

1. Fazer inventário de TODOS os imports entre os módulos atuais
   - Quais arquivos em shopman/ importam de adapters/?
   - Quais importam de backends/ (já removido em WP-A2)?
   - Quais importam modifiers.py?
   - Quais importam webhooks/?
   - Quais web/views importam de services/?

2. Mapear quais models são referenciados por quais views/handlers

3. Confirmar que NÃO há modelos em código que será movido para
   nelson/ (nelson/ NÃO terá migrations — usa models do framework)

## Passo 2: Criar nelson/ como Django app

1. Criar `nelson/` no nível de `shopman/` (ambos dentro do mesmo
   projeto Django)
2. Criar `nelson/__init__.py`
3. Criar `nelson/apps.py`:
   ```python
   from django.apps import AppConfig

   class NelsonConfig(AppConfig):
       name = "nelson"
       verbose_name = "Nelson Boulangerie"
       default_auto_field = "django.db.models.BigAutoField"

       def ready(self):
           import nelson.flows  # noqa: F401 — registra flows no registry
   ```
4. Adicionar `"nelson"` ao INSTALLED_APPS em settings.py, APÓS
   `"shopman"`

## Passo 3: Mover flows de instância

1. Criar `nelson/flows.py`
2. Mover de `shopman/flows.py` para `nelson/flows.py`:
   - ManychatFlow
   - IFoodFlow
   - PosFlow
   - TotemFlow
   - WhatsAppFlow
   - WebFlow
   (São subclasses que estendem LocalFlow/RemoteFlow/MarketplaceFlow)
3. Manter em `shopman/flows.py`:
   - BaseFlow, LocalFlow, RemoteFlow, MarketplaceFlow
   - Registry (_registry), flow decorator, get_flow, dispatch
4. Em `nelson/flows.py`, importar de `shopman.flows`:
   ```python
   from shopman.flows import flow, LocalFlow, RemoteFlow, MarketplaceFlow

   @flow("pos")
   class PosFlow(LocalFlow):
       """Counter POS."""
       pass

   @flow("manychat")
   class ManychatFlow(RemoteFlow):
       """ManyChat / WhatsApp."""
       pass

   # ... etc
   ```
5. O import em `nelson/apps.py:ready()` garante que os decorators
   @flow() executam e registram no registry do framework

## Passo 4: Mover adapters de instância

1. Criar `nelson/adapters/`
2. Mover de `shopman/adapters/` para `nelson/adapters/`:
   - payment_efi.py
   - payment_stripe.py
   - notification_manychat.py
   - otp_manychat.py
3. Se existirem arquivos de fiscal e accounting em adapters/ (movidos
   de backends/ no WP-A2), mover para nelson/adapters/:
   - fiscal_focus.py
   - fiscal_mock.py
   - accounting_contaazul.py
   - accounting_mock.py
4. Manter em `shopman/adapters/`:
   - __init__.py (get_adapter framework)
   - payment_mock.py
   - notification_console.py
   - notification_email.py
   - notification_sms.py
   - notification_webhook.py
   - stock_internal.py (se existir)
5. Atualizar os dotted paths em settings.py:
   Onde era `"shopman.adapters.payment_efi"` → `"nelson.adapters.payment_efi"`

## Passo 5: Mover modifiers de instância

1. Criar `nelson/modifiers.py`
2. Mover de `shopman/modifiers.py` para `nelson/modifiers.py`:
   - D1DiscountModifier
   - HappyHourModifier
   - EmployeeDiscountModifier
3. Se DiscountModifier/PromotionModifier forem genéricos (qualquer loja
   pode ter promoções), mantê-los em `shopman/modifiers.py`
4. Se forem específicos, mover também
5. Atualizar SHOPMAN_MODIFIERS em settings.py:
   `"shopman.modifiers.D1DiscountModifier"` → `"nelson.modifiers.D1DiscountModifier"`

## Passo 6: Mover webhooks

1. Criar `nelson/webhooks/`
2. Mover `shopman/webhooks/efi.py` e `stripe.py` para `nelson/webhooks/`
3. Mover `shopman/webhooks/urls.py` para `nelson/webhooks/urls.py`
4. Atualizar `project/urls.py` para incluir `nelson.webhooks.urls`
   em vez de `shopman.webhooks.urls`
5. Remover `shopman/webhooks/` (diretório vazio)

## Passo 7: Mover management commands de instância

1. Criar `nelson/management/commands/`
2. Mover `shopman/management/commands/seed.py` para
   `nelson/management/commands/seed.py`
3. Manter em `shopman/management/commands/`:
   - cleanup_d1.py (framework utility)
   - cleanup_stale_sessions.py (framework utility)
   - suggest_production.py (framework utility)

## Passo 8: Organizar web/templates

As views e templates do storefront são framework (qualquer loja precisa
de catalog, cart, checkout). Ficam em `shopman/web/`.

1. Manter TODAS as views em `shopman/web/views/`
2. Manter TODOS os templates em `shopman/web/templates/`
3. Se houver templates com branding/assets específicos da Nelson,
   criar overrides em `nelson/templates/` (Django template loader
   prioriza templates do projeto sobre os do app)
4. NÃO mover views para nelson/ — as views são framework
5. Se houver views MUITO específicas (ex: uma landing page da Nelson),
   criar em nelson/web/views/ e registrar em urls.py da instância

## Passo 9: Atualizar settings.py

```python
INSTALLED_APPS = [
    # ... Django + third-party ...
    # Core (Layer 0) — nomes atuais, renaming no WP-A5
    "shopman.utils",
    "shopman.offerman",
    "shopman.stockman",
    "shopman.craftsman",
    "shopman.omniman",
    "shopman.payman",
    "shopman.guestman",
    "shopman.doorman",
    # Contrib sub-apps
    "shopman.offerman.contrib.admin_unfold",
    "shopman.stockman.contrib.admin_unfold",
    # ... etc
    # Framework (Layer 1)
    "shopman",
    # Instance (Layer 2)
    "nelson",
]

# Atualizar TODOS os dotted paths para refletir as novas localizações
SHOPMAN_MODIFIERS = [
    "shopman.handlers.pricing.ItemPricingModifier",
    "nelson.modifiers.D1DiscountModifier",
    "nelson.modifiers.DiscountModifier",
    "nelson.modifiers.EmployeeDiscountModifier",
    "nelson.modifiers.HappyHourModifier",
]

SHOPMAN_PAYMENT_ADAPTERS = {
    "pix": "nelson.adapters.payment_efi",
    "card": "nelson.adapters.payment_stripe",
    "mock": "shopman.adapters.payment_mock",
}

# ... etc para todos os adapters
```

## Passo 10: Atualizar imports

Fazer busca e replace em todo o projeto:
1. `from shopman.modifiers import D1` → `from nelson.modifiers import D1`
2. `from shopman.webhooks` → `from nelson.webhooks`
3. `from shopman.adapters.payment_efi` → `from nelson.adapters.payment_efi`
4. Etc.

Usar grep para garantir que NÃO restam imports da localização antiga.

## Passo 11: Atualizar testes

Testes que importam de localizações antigas precisam ser atualizados.
Testes do framework ficam em `shopman/tests/`.
Testes da instância (se necessário) ficam em `nelson/tests/`.

## Passo 12: Atualizar Makefile

Se o Makefile referencia paths antigos, atualizar.

## Verificação
- `make test` (todos — CRÍTICO, muitos imports mudam)
- `make lint`
- `make run` — confirmar que o storefront carrega
- Confirmar que admin funciona
- Confirmar que seed funciona: `python manage.py seed`
- Grep: `from shopman.webhooks` não deve existir
- Grep: `from shopman.modifiers import D1` não deve existir
  (agora em nelson)
- Verificar que `shopman/` não contém código específico da padaria
- Verificar que `nelson/` não contém código de framework
```

---

## WP-A5: Renaming Core Apps — Nomes de Persona

**Status:** concluído
**Risco:** alto (renomeia packages, models, imports em todo o projeto)
**Escopo:** shopman-core/ inteiro + todos os imports no framework e instância
**Pré-requisito:** WP-A4 concluído (reorganização de pastas completa)

### Prompt

```
Execute o WP-A5 do ARCH-PLAN.md.

## Contexto

Os Core apps (Layer 0) serão renomeados para nomes de persona.
Migrações serão zeradas. O seed repopula os dados.

## Mapa de Renaming

| Atual | Novo | Pip package | Python namespace |
|---|---|---|---|
| shopman.omniman | shopman.omniman | shopman-omniman | shopman.omniman |
| shopman.stockman | shopman.stockman | shopman-stockman | shopman.stockman |
| shopman.craftsman | shopman.craftsman | shopman-craftsman | shopman.craftsman |
| shopman.offerman | shopman.offerman | shopman-offerman | shopman.offerman |
| shopman.guestman | shopman.guestman | shopman-guestman | shopman.guestman |
| shopman.doorman | shopman.doorman | shopman-doorman | shopman.doorman |
| shopman.payman | shopman.payman | shopman-payman | shopman.payman |
| shopman.utils | shopman.utils | shopman-utils | shopman.utils (sem mudança) |

## Passo 1: Planejar a cascata de mudanças

ANTES de alterar qualquer arquivo:

1. Grep por cada import antigo em TODO o projeto:
   - `from shopman.omniman` — contar ocorrências
   - `from shopman.stockman` — contar ocorrências
   - `from shopman.craftsman` — contar ocorrências
   - `from shopman.offerman` — contar ocorrências
   - `from shopman.guestman` — contar ocorrências
   - `from shopman.doorman` — contar ocorrências
   - `from shopman.payman` — contar ocorrências
   - `import shopman.omniman` — contar ocorrências

2. Listar TODOS os arquivos que precisam mudar

3. Verificar que nenhum nome novo conflita com módulos existentes

## Passo 2: Renomear diretórios no core

Para cada app (exemplo com ordering → omniman):

1. Renomear diretório:
   `shopman-core/omniman/shopman/ordering/` → `shopman-core/omniman/shopman/omniman/`

2. Renomear o diretório pai:
   `shopman-core/omniman/` → `shopman-core/omniman/`

3. Atualizar `apps.py`:
   ```python
   class OmnimanConfig(AppConfig):
       name = "shopman.omniman"
       verbose_name = "Pedidos"
       default_auto_field = "django.db.models.BigAutoField"
   ```

4. Atualizar `pyproject.toml`:
   - name = "shopman-omniman"
   - packages = ["shopman/omniman"]

5. Atualizar TODOS os imports INTERNOS do app (entre arquivos do mesmo app):
   - `from shopman.omniman.models import` → `from shopman.omniman.models import`
   - `from shopman.omniman.services import` → `from shopman.omniman.services import`

6. Atualizar test settings e conftest:
   - `ordering_test_settings.py` → `omniman_test_settings.py`
   - INSTALLED_APPS dentro do test settings

7. Atualizar contrib sub-apps:
   - `shopman.omniman.contrib.admin_unfold` → `shopman.omniman.contrib.admin_unfold`

8. Atualizar cross-app references:
   - `shopman.omniman.protocols` re-exports from payments →
     `shopman.omniman.protocols` re-exports from payman

Repetir para CADA app no mapa de renaming.

## Passo 3: Atualizar o framework (shopman/)

Busca e replace em TODOS os arquivos de `shopman/`:
- `from shopman.omniman` → `from shopman.omniman`
- `from shopman.stockman` → `from shopman.stockman`
- `from shopman.craftsman` → `from shopman.craftsman`
- `from shopman.offerman` → `from shopman.offerman`
- `from shopman.guestman` → `from shopman.guestman`
- `from shopman.doorman` → `from shopman.doorman`
- `from shopman.payman` → `from shopman.payman`

Arquivos críticos a verificar:
- `shopman/flows.py` (imports de ordering models)
- `shopman/services/*.py` (imports de todos os core apps)
- `shopman/handlers/*.py` (imports de ordering, stocking, etc.)
- `shopman/protocols.py` (re-exports de ordering, payments)
- `shopman/apps.py` (signal imports)
- `shopman/config.py`
- `shopman/web/views/*.py` (imports de offering, ordering)

## Passo 4: Atualizar a instância (nelson/)

Busca e replace em `nelson/`:
- Mesmas substituições do Passo 3

## Passo 5: Atualizar settings.py

```python
INSTALLED_APPS = [
    # Core (Layer 0)
    "shopman.utils",
    "shopman.offerman",
    "shopman.stockman",
    "shopman.craftsman",
    "shopman.omniman",
    "shopman.payman",
    "shopman.guestman",
    "shopman.doorman",
    # Contrib
    "shopman.offerman.contrib.admin_unfold",
    "shopman.stockman.contrib.admin_unfold",
    # Framework (Layer 1)
    "shopman",
    # Instance (Layer 2)
    "nelson",
]
```

## Passo 6: Zerar migrações

1. Deletar TODAS as migrations de TODOS os core apps
2. Deletar TODAS as migrations de shopman (framework)
3. `python manage.py makemigrations` para gerar novas migrations
   com os app_labels corretos (omniman, stockman, etc.)
4. `python manage.py migrate` (fresh DB)
5. `python manage.py seed` (repopular dados)

## Passo 7: Verificar CLAUDE.md e docs

Atualizar TODAS as referências em documentação:
- CLAUDE.md (estrutura do projeto, imports, exemplos)
- docs/ (guias, referência, ADRs)
- DEBT-PLAN.md (se ainda existir — atualizar paths)
- ARCH-PLAN.md (atualizar paths)

## Passo 8: Convenção de zero residuals

Busca final — NENHUM destes termos deve aparecer no código:
- `shopman.omniman` (exceto em git history)
- `shopman.stockman`
- `shopman.craftsman`
- `shopman.offerman`
- `shopman.guestman`
- `shopman.doorman` (cuidado: `shopman.doorman` é auth, mas Django tem
  seu próprio `django.contrib.auth` — não confundir)
- `shopman.payman`

Grep CADA um. Zero hits = sucesso.

## Verificação
- `make test` (todos — CRÍTICO)
- `make lint`
- `make run` — confirmar que tudo carrega
- `make seed` — confirmar que seed funciona
- Admin: confirmar que sidebar mostra "Pedidos", "Estoque", etc.
  (verbose_names), não "Omniman", "Stockman"
- Zero residuals grep
```

---

## Visão de Organização Final

Após DEBT-PLAN + ARCH-PLAN completo:

```
shopman-core/               Layer 0 — pip packages
├── omniman/                    Pedidos omnichannel
├── stockman/                   Estoque
├── craftsman/                  Produção
├── offerman/                   Catálogo
├── guestman/                   CRM
├── doorman/                    Auth
├── payman/                     Pagamentos
└── utils/                      Utilitários compartilhados

shopman/                    Layer 1 — framework pip-instalável
├── flows, services, handlers, adapters, models, web, api, admin

nelson/                     Layer 2 — instância Nelson Boulangerie
├── flows, adapters, modifiers, webhooks, seed

project/                    Django project config
```

**Adoção:**
1. `pip install shopman` (puxa core + framework)
2. Criar projeto (startproject ou cookiecutter)
3. Configurar settings (adapters, modifiers, channels)
4. Popular dados (seed ou admin)
5. Rodar

**Futuro:** `nelson/` é o exemplo de instância. Cookiecutter gera o
equivalente para outro negócio.

## Ordem de Execução

**Fase 1 — DEBT-PLAN (bugs):**
D1 → D4 → D2 → D3

**Fase 2 — ARCH-PLAN (arquitetura):**
A1 → A2 → A3 → A4 → A5
