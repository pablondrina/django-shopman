# REFACTOR-SHOPMAN-PLAN.md — Tréplica Final

> **O Core é um kernel — precisa de robustez (Protocol, Registry, RLock).**
> **Shopman é cola — precisa de simplicidade (base classes, pools, hooks).**
> **Django Salesman ensina: conte seus pontos de extensão. Cada um tem um custo.**

---

## Contexto

Análise em 5 rodadas (análise → plano → autocrítica → tréplica → revisão Salesman)
identificou que Shopman precisa de um mecanismo formal de extensibilidade para
os 4 pontos onde há variação real entre instâncias: Payment, Notification,
Customer resolution e Fiscal.

**Diagnóstico:**
- `get_adapter()` ad-hoc resolve adapters por módulo (não por classe)
- `_payment_backend_cache` global thread-unsafe no payment handler
- `services/customer.py` com 319 linhas de if/elif por canal
- 5 locais criando `Directive.objects.create()` com copy-paste
- 3 patterns de error handling incompatíveis
- ~15 hardcodes de instância (DDD "43", channel "web", etc.)
- `services/pricing.py` (34 linhas) e `services/production.py` (55 linhas) são dead code

**Resultado esperado:**
- 4 extension points explícitos via Pool pattern (Salesman-style)
- Error handling uniforme (ShopmanError + BaseHandler)
- Settings genéricos com defaults sensatos (ShopmanSettings)
- Zero hardcodes de instância no framework
- Services limpos, sem mortos

**Relação com planos anteriores:**
- DEBT-PLAN (D1-D4) e ARCH-PLAN (A1-A5) estão concluídos
- Este plano constrói em cima: backends/ já unificados em adapters/,
  pipeline dead code já removido, registro já via settings

**Ordem de execução:** Fase 1 primeiro (alicerce). Fases 2-4 são independentes
entre si mas dependem da Fase 1. Fase 5 no final.

---

## Fase 1 — Pools + Alicerce (7 WPs)

Criar os 4 extension points + ShopmanError + directives helper + conf.
Nenhum consumidor muda nesta fase — os pools coexistem com o código atual.

---

### WP-1E: ShopmanError

**Status:** concluído
**Risco:** zero (cria arquivo novo, ninguém consome ainda)

#### Prompt

```
Execute o WP-1E do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

O projeto tem 3 patterns de error handling incompatíveis:
- Handlers: except Exception → log + set message.status = "failed"
- Services: except Exception → log + return (silencioso)
- Views: except Exception → pass (corrigido no DEBT-PLAN D4 para logger.warning)

Precisamos de uma exceção base para o framework que permita distinguir
erros de negócio (retry/escalate) de bugs (crash).

## Alteração: Criar shopman-app/shopman/exceptions.py

Criar o arquivo com:

```python
"""
Shopman exceptions — structured errors for the framework layer.

Business errors carry a code, message, and context dict.
Handlers catch ShopmanError for retry/escalate; Exception means bug.
"""


class ShopmanError(Exception):
    """Base exception for business errors in the framework layer."""

    def __init__(self, code, message="", **context):
        self.code = code
        self.message = message or code
        self.context = context
        super().__init__(f"[{code}] {self.message}")
```

Só isso. Sem subclasses ainda — serão criadas quando consumidores precisarem.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-1G: ShopmanSettings

**Status:** concluído
**Risco:** zero (cria arquivo novo, ninguém consome ainda)
**Depende de:** nada

#### Prompt

```
Execute o WP-1G do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

~15 hardcodes de instância estão espalhados pelo código:
- CHANNEL_REF = "web" em web/constants.py
- DDD "43" em phone normalization
- operator email em notification handlers
- TTLs, listing refs, collection icons

Precisamos de um ponto central onde Shopman lê configurações do Django
settings, com defaults genéricos. Pattern: propriedades simples, como
o Salesman AppSettings. SEM dataclass, SEM _LazySettings proxy.

## Passo 1: Entender hardcodes existentes

ANTES de criar, fazer inventário. Grep por:
- `"web"` como channel ref em shopman/web/ (constante CHANNEL_REF ou similar)
- `"43"` como DDD default em shopman/ e shopman-core/
- `OPERATOR` ou `operator_email` em shopman/
- `STOREFRONT` em shopman/
- Constantes hardcoded em shopman/web/constants.py

NÃO alterar nenhum consumidor ainda — só criar o arquivo de settings.
Os consumidores serão migrados em WP-4A.

## Passo 2: Criar shopman-app/shopman/conf.py (NÃO config.py — já existe)

ATENÇÃO: `config.py` já existe e contém ChannelConfig. Este arquivo
deve se chamar `conf.py` para seguir a convenção do Core (ex: stockman/conf.py).

Criar `shopman-app/shopman/conf.py`:

```python
"""
Shopman settings — configurable defaults for the framework layer.

Instance overrides via Django settings (SHOPMAN_*).
Shopman reads; instance writes.
"""

from django.conf import settings


class ShopmanSettings:
    """
    Centralized settings with sensible defaults.

    Usage:
        from shopman.conf import shopman_settings
        channel = shopman_settings.STOREFRONT_CHANNEL
    """

    @property
    def STOREFRONT_CHANNEL(self):
        """Channel ref for the web storefront."""
        return getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL", "web")

    @property
    def DEFAULT_PHONE_DDD(self):
        """Default area code for phone normalization (e.g., "43")."""
        return getattr(settings, "SHOPMAN_DEFAULT_PHONE_DDD", "")

    @property
    def OPERATOR_EMAIL(self):
        """Email for operator notifications and alerts."""
        return getattr(settings, "SHOPMAN_OPERATOR_EMAIL", "")

    @property
    def OPERATOR_PHONE(self):
        """Phone for operator SMS/WhatsApp alerts."""
        return getattr(settings, "SHOPMAN_OPERATOR_PHONE", "")

    @property
    def PIX_TIMEOUT_MINUTES(self):
        """Default PIX payment timeout."""
        return getattr(settings, "SHOPMAN_PIX_TIMEOUT_MINUTES", 15)

    @property
    def CONFIRMATION_TIMEOUT_MINUTES(self):
        """Default optimistic confirmation timeout."""
        return getattr(settings, "SHOPMAN_CONFIRMATION_TIMEOUT_MINUTES", 5)


shopman_settings = ShopmanSettings()
```

Notas:
- Cada property mapeia SHOPMAN_* do Django settings
- Defaults são GENÉRICOS (vazios ou sensatos), nunca específicos de instância
- Não incluir properties para coisas que já estão no ChannelConfig
  (PIX_TIMEOUT e CONFIRMATION_TIMEOUT são defaults globais; ChannelConfig
  pode overridar por canal)

## Verificação
- `make test-shopman-app`
- `make lint`
- Confirmar que `config.py` (ChannelConfig) não foi alterado
```

---

### WP-1F: directives.queue() helper

**Status:** concluído
**Risco:** zero (cria arquivo novo, ninguém consome ainda)
**Depende de:** nada

#### Prompt

```
Execute o WP-1F do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

5+ locais criam Directives com o mesmo padrão copy-paste:

```python
# services/notification.py
Directive.objects.create(topic=TOPIC, payload={
    "order_ref": order.ref,
    "channel_ref": order.channel.ref if order.channel else "",
    "template": template,
})

# services/fiscal.py
Directive.objects.create(topic="fiscal.emit", payload={
    "order_ref": order.ref,
    "items": ...,
    "payment": ...,
})

# services/loyalty.py (provavelmente similar)
```

Todos repetem: topic, order_ref, channel_ref. O helper unifica.

## Alteração: Criar shopman-app/shopman/directives.py

```python
"""
Directive queue helper — single entry point for async work.

Instead of Directive.objects.create() scattered across services,
use directives.queue() for consistent payload structure.
"""

from shopman.omniman.models import Directive


def queue(topic, order, **extra):
    """
    Create a Directive for async processing.

    Always includes order_ref and channel_ref. Extra kwargs are
    merged into the payload.

    Usage:
        from shopman import directives
        directives.queue("notification.send", order, template="order_confirmed")
    """
    payload = {"order_ref": order.ref}
    if order.channel:
        payload["channel_ref"] = order.channel.ref
    payload.update(extra)
    return Directive.objects.create(topic=topic, payload=payload)
```

NÃO alterar os consumidores ainda — isso será feito em WP-2C.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-1A: PaymentMethod + Pool

**Status:** concluído
**Risco:** zero (cria arquivo novo, ninguém consome ainda)
**Depende de:** nada

#### Prompt

```
Execute o WP-1A do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

O payment handler hoje usa um global cache thread-unsafe:

```python
# handlers/payment.py (linhas 32-54)
_payment_backend_cache: PaymentBackend | None = None

def _get_payment_backend() -> PaymentBackend | None:
    global _payment_backend_cache
    if _payment_backend_cache is None:
        path = getattr(settings, "SHOPMAN_PAYMENT_BACKEND", "...")
        module = importlib.import_module(module_path)
        _payment_backend_cache = getattr(module, class_name)()
    return _payment_backend_cache
```

E o `get_adapter()` em adapters/__init__.py resolve payment como módulo,
não como classe:

```python
# adapters/__init__.py
_DEFAULTS = {
    "payment": {
        "pix": "shopman.adapters.payment_mock",
        "card": "shopman.adapters.payment_mock",
    },
}
```

O Pool pattern substitui AMBOS os mecanismos para payment.

## Alteração: Criar shopman-app/shopman/payment.py

```python
"""
Payment methods — Pool pattern (Salesman-inspired).

Base class + lazy pool. Instance provides concrete methods.

Usage:
    from shopman.payment import payment_methods_pool

    method = payment_methods_pool.get_method("pix")
    result = method.create_intent(order)

Settings:
    SHOPMAN_PAYMENT_METHODS = [
        "nelson.adapters.payment_efi.EfiPixMethod",
        "nelson.adapters.payment_stripe.StripeCardMethod",
    ]
"""

from __future__ import annotations


class PaymentMethod:
    """
    Base payment method. Subclass in instance code.

    Each method has an identifier (e.g., "pix", "card") and implements
    the payment lifecycle: create → capture → refund.
    """

    identifier: str = ""
    label: str = ""

    def create_intent(self, order, **kwargs):
        """Create payment intent. Return dict with intent_id, status, metadata."""
        raise NotImplementedError

    def capture(self, intent_ref, amount_q, **kwargs):
        """Capture authorized payment. Return dict with success, transaction_id."""
        raise NotImplementedError

    def refund(self, intent_ref, amount_q=None, **kwargs):
        """Refund full or partial. Return dict with success, refund_id."""
        raise NotImplementedError

    def cancel(self, intent_ref):
        """Cancel unpaid intent."""
        raise NotImplementedError

    def get_status(self, intent_ref):
        """Check current payment status. Return status string."""
        raise NotImplementedError

    def get_urls(self):
        """Return URL patterns for webhooks (e.g., PIX callback)."""
        return []


class PaymentMethodsPool:
    """
    Lazy pool of payment methods loaded from settings.

    Methods are instantiated once on first access.
    Use reset() in tests to clear the cache.
    """

    def __init__(self):
        self._methods = None

    def get_methods(self):
        if self._methods is None:
            from django.conf import settings
            from django.utils.module_loading import import_string

            self._methods = [
                import_string(path)()
                for path in getattr(settings, "SHOPMAN_PAYMENT_METHODS", [])
            ]
        return self._methods

    def get_method(self, identifier):
        """Get a payment method by identifier. Returns None if not found."""
        for method in self.get_methods():
            if method.identifier == identifier:
                return method
        return None

    def get_urls(self):
        """Collect webhook URL patterns from all payment methods."""
        from django.urls import include, path

        urls = []
        for method in self.get_methods():
            method_urls = method.get_urls()
            if method_urls:
                urls.append(
                    path(f"payment/{method.identifier}/", include(method_urls))
                )
        return urls

    def reset(self):
        """Clear cached methods. Use in tests."""
        self._methods = None


payment_methods_pool = PaymentMethodsPool()
```

NÃO alterar handlers/payment.py nem adapters/ ainda — serão migrados
em WP-2D (services) e WP-3B (handlers).

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-1B: NotificationBackend + Pool

**Status:** concluído
**Risco:** zero (cria arquivo novo, ninguém consome ainda)
**Depende de:** nada

#### Prompt

```
Execute o WP-1B do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Notification hoje é resolvida via get_adapter("notification", channel=...)
que retorna um MÓDULO (não uma classe). O handler em handlers/notification.py
implementa uma fallback chain inline (primary → fallbacks from config).

O Pool unifica: uma lista de backends, cada um com identifier e send().
A fallback chain vira a ORDEM no pool (configurada via settings).

## Passo 1: Ler o estado atual

1. Ler shopman-app/shopman/handlers/notification.py COMPLETO para entender
   a fallback chain e como os adapters são chamados
2. Ler shopman-app/shopman/adapters/notification_console.py para entender
   a interface atual dos adapters

## Passo 2: Criar shopman-app/shopman/notification.py

```python
"""
Notification backends — Pool pattern (Salesman-inspired).

Base class + lazy pool. Instance provides concrete backends.
Pool order = fallback chain (first available backend wins).

Usage:
    from shopman.notification import notification_pool

    backend = notification_pool.get_backend("email")
    backend.send(event="order_confirmed", recipient="...", context={...})

Settings:
    SHOPMAN_NOTIFICATION_BACKENDS = [
        "nelson.adapters.notification_email.EmailBackend",
        "nelson.adapters.notification_console.ConsoleBackend",
    ]
"""

from __future__ import annotations


class NotificationBackend:
    """
    Base notification backend. Subclass in instance code.

    Each backend has an identifier (e.g., "email", "sms", "console")
    and implements send(). is_available() gates whether this backend
    can be used (e.g., missing credentials → False).
    """

    identifier: str = ""
    label: str = ""

    def send(self, *, event, recipient, context):
        """
        Send a notification.

        Returns dict with at least {"success": bool}.
        May include message_id, error, etc.
        """
        raise NotImplementedError

    def is_available(self):
        """Whether this backend is currently usable."""
        return True


class NotificationPool:
    """
    Lazy pool of notification backends loaded from settings.

    Backends are tried in order (fallback chain).
    Use reset() in tests to clear the cache.
    """

    def __init__(self):
        self._backends = None

    def get_backends(self):
        if self._backends is None:
            from django.conf import settings
            from django.utils.module_loading import import_string

            self._backends = [
                import_string(path)()
                for path in getattr(settings, "SHOPMAN_NOTIFICATION_BACKENDS", [])
            ]
        return self._backends

    def get_backend(self, identifier):
        """Get a backend by identifier. Returns None if not found."""
        for backend in self.get_backends():
            if backend.identifier == identifier:
                return backend
        return None

    def get_available(self):
        """Return backends that are currently available, in order."""
        return [b for b in self.get_backends() if b.is_available()]

    def reset(self):
        """Clear cached backends. Use in tests."""
        self._backends = None


notification_pool = NotificationPool()
```

NÃO alterar handlers/notification.py nem adapters/notification_*.py
ainda — serão migrados em WP-3C.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-1C: CustomerResolver + Pool

**Status:** concluído
**Risco:** zero (cria arquivo novo, ninguém consome ainda)
**Depende de:** nada

#### Prompt

```
Execute o WP-1C do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

O `services/customer.py` tem 319 linhas com 4 estratégias de resolução
hardcoded em if/elif:

```python
if handle_type == "manychat":
    customer = _handle_manychat(order)
elif channel_ref == "ifood":
    customer = _handle_ifood(order)
elif channel_ref == "balcao":
    customer = _handle_balcao(order)
else:
    customer = _handle_phone(order)
```

Cada strategy está em ~50 linhas de funções privadas. Tudo instance-specific
(ManyChat, iFood, balcão, CPF são de Nelson — outro negócio teria
estratégias diferentes).

O Pool pattern transforma: cada resolver é uma classe na instance (nelson/),
o service usa o pool para delegar.

## Alteração: Criar shopman-app/shopman/customer.py

```python
"""
Customer resolvers — Pool pattern (Salesman-inspired).

Base class + lazy pool. Instance provides concrete resolvers.
Each resolver handles a specific identification strategy
(phone, ManyChat subscriber, iFood order, etc.).

Usage:
    from shopman.customer import customer_resolver_pool

    resolver = customer_resolver_pool.get_resolver("manychat")
    result = resolver.resolve(order)

Settings:
    SHOPMAN_CUSTOMER_RESOLVERS = [
        "nelson.resolvers.PhoneResolver",
        "nelson.resolvers.ManychatResolver",
        "nelson.resolvers.IFoodResolver",
        "nelson.resolvers.BalcaoResolver",
    ]
"""

from __future__ import annotations


class CustomerResolver:
    """
    Base customer resolver. Subclass in instance code.

    Each resolver handles one identification strategy (phone, subscriber_id,
    external order ID, document, etc.). The pool tries resolvers by
    identifier match (handle_type → channel_ref → default).
    """

    identifier: str = ""
    is_default: bool = False

    def resolve(self, order):
        """
        Resolve or create a customer from order context.

        Args:
            order: Order with data, channel, handle_ref, etc.

        Returns:
            dict with:
                found (bool): Whether a customer was resolved
                customer_ref (str): The customer ref (if found)
                created (bool): Whether a new customer was created
        """
        raise NotImplementedError


class CustomerResolverPool:
    """
    Lazy pool of customer resolvers loaded from settings.

    Resolution strategy: try by handle_type, then by channel_ref,
    then fall back to the default resolver.
    """

    def __init__(self):
        self._resolvers = None

    def get_resolvers(self):
        if self._resolvers is None:
            from django.conf import settings
            from django.utils.module_loading import import_string

            self._resolvers = [
                import_string(path)()
                for path in getattr(settings, "SHOPMAN_CUSTOMER_RESOLVERS", [])
            ]
        return self._resolvers

    def get_resolver(self, identifier):
        """Get a resolver by identifier. Returns None if not found."""
        for resolver in self.get_resolvers():
            if resolver.identifier == identifier:
                return resolver
        return None

    def get_default(self):
        """Get the default resolver (is_default=True). Returns None if none set."""
        for resolver in self.get_resolvers():
            if resolver.is_default:
                return resolver
        return None

    def reset(self):
        """Clear cached resolvers. Use in tests."""
        self._resolvers = None


customer_resolver_pool = CustomerResolverPool()
```

NÃO alterar services/customer.py ainda — será reescrito em WP-2B.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-1D: FiscalBackend + Pool

**Status:** concluído
**Risco:** zero (cria arquivo novo, ninguém consome ainda)
**Depende de:** nada

#### Prompt

```
Execute o WP-1D do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Fiscal hoje é resolvido via get_adapter("fiscal") que retorna módulo
ou None. services/fiscal.py faz `if adapter is None: return` como
smart no-op. handlers/fiscal.py usa global cache idêntico ao payment.

O Pool substitui: uma classe base FiscalBackend com emit/cancel,
pool carregado do settings. Smart no-op = pool vazio.

## Alteração: Criar shopman-app/shopman/fiscal.py

```python
"""
Fiscal backends — Pool pattern (Salesman-inspired).

Base class + lazy pool. Instance provides concrete backends
(e.g., Focus NFC-e, mock).

Usage:
    from shopman.fiscal import fiscal_pool

    backend = fiscal_pool.get_backend()
    if backend:
        backend.emit(order_ref, items, payment, customer)

Settings:
    SHOPMAN_FISCAL_BACKENDS = [
        "nelson.adapters.fiscal_focus.FocusNFCeBackend",
    ]
"""

from __future__ import annotations


class FiscalBackend:
    """
    Base fiscal backend. Subclass in instance code.

    Fiscal backends emit and cancel tax documents (NFC-e, NF-e, etc.).
    """

    identifier: str = ""
    label: str = ""

    def emit(self, *, order_ref, items, payment, customer):
        """
        Emit fiscal document.

        Returns dict with at least:
            success (bool)
            access_key (str): The fiscal document access key
        """
        raise NotImplementedError

    def cancel(self, *, order_ref, access_key, reason=""):
        """
        Cancel fiscal document.

        Returns dict with at least:
            success (bool)
        """
        raise NotImplementedError


class FiscalPool:
    """
    Lazy pool of fiscal backends loaded from settings.

    Typically only one backend (or none). get_backend() returns
    the first, or None if pool is empty (smart no-op).
    """

    def __init__(self):
        self._backends = None

    def get_backends(self):
        if self._backends is None:
            from django.conf import settings
            from django.utils.module_loading import import_string

            self._backends = [
                import_string(path)()
                for path in getattr(settings, "SHOPMAN_FISCAL_BACKENDS", [])
            ]
        return self._backends

    def get_backend(self, identifier=None):
        """
        Get a fiscal backend. If identifier is None, return the first.
        Returns None if pool is empty (no fiscal configured).
        """
        backends = self.get_backends()
        if identifier:
            for b in backends:
                if b.identifier == identifier:
                    return b
            return None
        return backends[0] if backends else None

    def reset(self):
        """Clear cached backends. Use in tests."""
        self._backends = None


fiscal_pool = FiscalPool()
```

NÃO alterar services/fiscal.py nem handlers/fiscal.py ainda — serão
migrados em WP-2C e WP-3F.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

## Fase 2 — Services (5 WPs)

Migrar services para usar pools e directives.queue().
Depende de: Fase 1 completa.

---

### WP-2A: Eliminar pricing.py e production.py

**Status:** concluído (pricing.py deletado; production.py mantido — tem 12 consumidores reais em production_flows.py)
**Risco:** baixo (dead code)
**Depende de:** nada (independente dos pools)

#### Prompt

```
Execute o WP-2A do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Dois services são dead code:

1. `services/pricing.py` (34 linhas) — wrapper trivial:
   ```python
   def resolve(sku, qty=1, channel=None):
       return CatalogService.price(sku, qty=Decimal(str(qty)), channel=channel)
   ```
   Chamado apenas em `services/__init__.py` (docstring) e testes.
   Callers devem chamar CatalogService.price() direto.

2. `services/production.py` (55 linhas) — 3 funções que só fazem logger.info():
   ```python
   def reserve_materials(work_order): logger.info(...)
   def emit_goods(work_order): logger.info(...)
   def notify(work_order, event): logger.info(...)
   ```
   Zero imports em todo o codebase (confirmado via grep).

## Passo 1: Verificar consumidores

Grep ANTES de deletar:
1. `from shopman.services.pricing` e `services.pricing` em todo shopman-app/
2. `from shopman.services.production` e `services.production` em todo shopman-app/
3. `pricing.resolve` em todo shopman-app/ (excluindo o próprio arquivo)

Se encontrar consumidores reais (além de docstrings, __init__.py, e testes),
PARAR e reportar.

## Passo 2: Deletar os arquivos

1. Deletar `shopman-app/shopman/services/pricing.py`
2. Deletar `shopman-app/shopman/services/production.py`

## Passo 3: Atualizar referências

1. Em `shopman-app/shopman/services/__init__.py`:
   - Remover as linhas do docstring que referenciam pricing e production
   - Preservar o resto do docstring intacto

2. Em testes que importam pricing.resolve:
   - Se o teste testa pricing.resolve diretamente → deletar o teste
   - Se o teste usa pricing.resolve como helper → substituir por
     `CatalogService.price(sku, qty=Decimal(str(qty)), channel=channel)`

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-2B: customer.py → usa pool

**Status:** concluído
**Risco:** médio (reescreve service inteiro)
**Depende de:** WP-1C (CustomerResolver pool)

#### Prompt

```
Execute o WP-2B do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

`services/customer.py` tem 319 linhas com:
- 4 estratégias hardcoded em if/elif (_handle_manychat, _handle_ifood,
  _handle_balcao, _handle_phone)
- ~15 funções privadas helpers
- Import de guestman models (CustomerIdentifier, CustomerAddress, TimelineEvent)

A lógica das 4 estratégias é instance-specific (Nelson). O service
genérico deve delegar para o pool.

## Passo 1: Ler o arquivo atual COMPLETO

Ler shopman-app/shopman/services/customer.py inteiro (319 linhas).
Entender TUDO que ensure() faz:
1. Resolve/create customer (via strategies)
2. Salva customer_ref em order.data
3. Salva delivery address
4. Cria timeline event
5. Atualiza insights

Os passos 3-5 são pós-resolução e devem permanecer no service (são
genéricos — qualquer instância quer salvar endereço e timeline).

## Passo 2: Criar resolvers na instance

Criar `shopman-app/nelson/resolvers.py` com as 4 estratégias extraídas
de customer.py. Cada resolver é uma classe que herda CustomerResolver.

Estrutura:

```python
"""
Nelson Boulangerie — Customer resolvers.

Instance-specific strategies for customer resolution.
Registered via SHOPMAN_CUSTOMER_RESOLVERS in settings.
"""

from __future__ import annotations

import logging
import uuid

from shopman.customer import CustomerResolver

logger = logging.getLogger(__name__)


class PhoneResolver(CustomerResolver):
    """Resolve by phone number. Default fallback."""
    identifier = "phone"
    is_default = True

    def resolve(self, order):
        # Extrair lógica de _handle_phone() do customer.py atual
        # Usar _get_customer_service(), _normalize_phone_safe(), etc.
        # Retornar {"found": bool, "customer_ref": str, "created": bool}
        ...


class ManychatResolver(CustomerResolver):
    """Resolve ManyChat subscribers by subscriber_id."""
    identifier = "manychat"

    def resolve(self, order):
        # Extrair lógica de _handle_manychat()
        ...


class IFoodResolver(CustomerResolver):
    """Resolve iFood orders by external order ID."""
    identifier = "ifood"

    def resolve(self, order):
        # Extrair lógica de _handle_ifood()
        ...


class BalcaoResolver(CustomerResolver):
    """Resolve balcão customers by CPF or phone."""
    identifier = "balcao"

    def resolve(self, order):
        # Extrair lógica de _handle_balcao()
        ...
```

IMPORTANTE: Cada resolver deve conter TODA a lógica que antes estava
nas funções _handle_*. Incluindo:
- _find_by_identifier() → inline ou helper local
- _add_identifier() → inline ou helper local
- _maybe_update_name() → inline ou helper local
- _split_name() → helper local
- _normalize_phone_safe() → usar shopman.utils.phone.normalize_phone
- _get_customer_service() → importar diretamente

O retorno de resolve() deve ser um dict:
```python
{"found": True, "customer_ref": "CLI-ABCD1234", "created": False}
{"found": True, "customer_ref": "MC-EFGH5678", "created": True}
{"found": False}
```

## Passo 3: Reescrever services/customer.py

O service fica com ~40-50 linhas (não 15 — precisa manter os passos
pós-resolução):

```python
"""
Customer resolution service.

Delegates resolution to CustomerResolver pool.
Post-resolution: saves address, timeline, insights.
"""

from __future__ import annotations

import logging

from shopman.customer import customer_resolver_pool

logger = logging.getLogger(__name__)


def ensure(order) -> None:
    """
    Resolve or create the customer for the order.

    Strategy: pool tries resolver by handle_type → channel_ref → default.
    Post-resolution: saves delivery address, timeline event, insights.

    SYNC — needs customer_ref before proceeding.
    """
    if not _customers_available():
        return

    channel_ref = order.channel.ref if order.channel else ""
    handle_type = getattr(order, "handle_type", "") or ""

    resolver = (
        customer_resolver_pool.get_resolver(handle_type)
        or customer_resolver_pool.get_resolver(channel_ref)
        or customer_resolver_pool.get_default()
    )
    if not resolver:
        return

    try:
        result = resolver.resolve(order)
    except Exception as exc:
        logger.warning("customer.ensure: resolver failed for order %s: %s", order.ref, exc)
        return

    if not result or not result.get("found"):
        return

    customer_ref = result["customer_ref"]
    if order.data.get("customer_ref") != customer_ref:
        order.data["customer_ref"] = customer_ref
        order.save(update_fields=["data", "updated_at"])

    # Post-resolution hooks (generic — any instance wants these)
    _save_delivery_address(customer_ref, order)
    _create_timeline_event(customer_ref, order)
    _update_insights(customer_ref)
```

Os helpers _save_delivery_address, _create_timeline_event, _update_insights
permanecem no service (são genéricos). Adaptar para receber customer_ref
em vez de customer object, se necessário.

_customers_available() permanece (guard para quando guestman não está instalado).

## Passo 4: Atualizar nelson/apps.py

Adicionar import dos resolvers (se necessário para registro).

## Passo 5: Atualizar settings

Em project/settings.py, adicionar:

```python
SHOPMAN_CUSTOMER_RESOLVERS = [
    "nelson.resolvers.PhoneResolver",
    "nelson.resolvers.ManychatResolver",
    "nelson.resolvers.IFoodResolver",
    "nelson.resolvers.BalcaoResolver",
]
```

## Verificação
- `make test-shopman-app`
- `make lint`
- Confirmar que nenhum teste importa _handle_manychat, _handle_ifood, etc.
  diretamente (se importar, atualizar para usar resolver)
```

---

### WP-2C: notification/loyalty/fiscal → directives.queue()

**Status:** concluído
**Risco:** baixo (simplificação, mesma semântica)
**Depende de:** WP-1F (directives.py)

#### Prompt

```
Execute o WP-2C do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

3 services criam Directives com copy-paste. Substituir por directives.queue().

## Alteração 1: shopman-app/shopman/services/notification.py

De:
```python
Directive.objects.create(topic=TOPIC, payload={
    "order_ref": order.ref,
    "channel_ref": order.channel.ref if order.channel else "",
    "template": template,
})
```

Para:
```python
from shopman import directives

def send(order, template: str) -> None:
    origin = (order.data or {}).get("origin_channel")
    extra = {"template": template}
    if origin:
        extra["origin_channel"] = origin
    directives.queue("notification.send", order, **extra)
    logger.info("notification.send: queued %s for order %s", template, order.ref)
```

Remover import de Directive. Remover constante TOPIC.

## Alteração 2: shopman-app/shopman/services/fiscal.py

De:
```python
Directive.objects.create(topic="fiscal.emit", payload={
    "order_ref": order.ref,
    "items": _build_fiscal_items(order),
    ...
})
```

Para:
```python
from shopman import directives

def emit(order) -> None:
    adapter = get_adapter("fiscal")  # manter guard por enquanto (WP-3F migrará)
    if adapter is None:
        return
    if (order.data or {}).get("nfce_access_key"):
        return
    directives.queue(
        "fiscal.emit", order,
        items=_build_fiscal_items(order),
        payment=(order.data or {}).get("payment", {}),
        customer=(order.data or {}).get("customer", {}),
    )
    logger.info("fiscal.emit: queued for order %s", order.ref)
```

Mesmo para cancel(). Remover import de Directive.

## Alteração 3: shopman-app/shopman/services/loyalty.py

Ler o arquivo primeiro. Se usa Directive.objects.create(), substituir
por directives.queue(). Se já usa outro mecanismo, adaptar.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-2D: payment.py → usa pool

**Status:** concluído
**Risco:** baixo
**Depende de:** WP-1A (PaymentMethod pool)

#### Prompt

```
Execute o WP-2D do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

services/payment.py usa get_adapter("payment", method=...) para resolver
o adapter. Deve passar a usar payment_methods_pool.get_method().

## Passo 1: Ler services/payment.py COMPLETO

Entender todas as funções e como usam get_adapter("payment", method=...).

## Passo 2: Substituir get_adapter por pool

Para cada chamada a get_adapter("payment", method=X):
- Substituir por payment_methods_pool.get_method(X)
- Ajustar chamadas se a interface mudou (get_adapter retorna módulo,
  pool retorna instância de PaymentMethod)

ATENÇÃO: A interface pode ser diferente. get_adapter retorna um módulo
e o caller chama funções do módulo. PaymentMethod é uma classe com
métodos. Se necessário, adaptar as chamadas.

Se a adaptação for complexa (muitas chamadas, interface incompatível),
PARAR e reportar — pode ser melhor fazer junto com WP-3B (handlers).

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-2E: stock.py → chamar Core direto

**Status:** concluído (já estava chamando Core direto — zero uso de get_adapter("stock"))
**Risco:** baixo
**Depende de:** nada

#### Prompt

```
Execute o WP-2E do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

services/stock.py já chama StockService.hold() direto (Core) para hold/fulfill.
Mas revert() ainda usa get_adapter("stock"). Unificar: tudo chama Core direto.

## Passo 1: Ler services/stock.py COMPLETO

Identificar TODOS os usos de get_adapter("stock") no arquivo.

## Passo 2: Substituir por chamada Core direta

Para cada get_adapter("stock"):
- Identificar qual método do adapter é chamado
- Encontrar o equivalente no Core (shopman.stockman.service.Stock ou
  shopman.stockman.services.*)
- Substituir, mantendo o mesmo tratamento de erro

## Passo 3: Limpar import

Remover `from shopman.adapters import get_adapter` se não for mais usado
no arquivo.

## Verificação
- `make test-shopman-app`
- `make test-stockman`
- `make lint`
```

---

## Fase 3 — Handlers (6 WPs)

Uniformizar handlers com BaseHandler e migrar para pools.
Depende de: Fase 1 (pools) e Fase 2 (services limpos).

---

### WP-3A: BaseHandler

**Status:** concluído
**Risco:** médio (muda interface de todos os handlers)

#### Prompt

```
Execute o WP-3A do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Cada handler implementa seu próprio try/except, retry logic, e escalation.
BaseHandler unifica o template method: handle() → execute() com retry/escalate.

## Passo 1: Ler o estado atual

Ler TODOS os handlers em shopman-app/shopman/handlers/ e entender:
1. Como cada handler chama message.status = "done" / "failed"
2. Como cada handler trata exceptions
3. Quais usam message.attempts para retry
4. Quais criam OperatorAlert em caso de falha

## Passo 2: Entender o dispatch

Ler shopman-core/omniman/shopman/omniman/dispatch.py para entender:
- Como dispatch chama handlers
- Se dispatch já faz retry (se sim, BaseHandler NÃO deve fazer)
- Como message.status e message.attempts são geridos

IMPORTANTE: Se o dispatch JÁ faz retry e gerencia status, o BaseHandler
deve ser MÍNIMO — apenas encapsular o try/except e delegar a semântica
de retry para o dispatch.

## Passo 3: Criar shopman-app/shopman/handlers/base.py

Baseado no entendimento do dispatch e dos handlers existentes, criar
BaseHandler com:
- topic (class attribute)
- handle(message, ctx) → chama execute(), gerencia status
- execute(message, ctx) → NotImplementedError
- _escalate(message, exc) → cria OperatorAlert

ADAPTAR o template method à semântica real do dispatch. Não inventar.

## Passo 4: Migrar UM handler simples como teste

Escolher o handler mais simples (ex: confirmation.py, 57 linhas) e
migrá-lo para usar BaseHandler. Confirmar que testes passam.

NÃO migrar os outros handlers ainda — serão feitos nos WPs seguintes.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-3B: payment handlers → pool

**Status:** concluído
**Risco:** médio-alto (452 linhas, global cache)
**Depende de:** WP-1A (pool), WP-3A (BaseHandler)

#### Prompt

```
Execute o WP-3B do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

handlers/payment.py (452 linhas) tem:
- _payment_backend_cache global (thread-unsafe)
- _get_payment_backend() lazy loader
- 7 handler classes (PaymentCaptureHandler, PaymentRefundHandler,
  PixGenerateHandler, PixTimeoutHandler, PaymentTimeoutHandler,
  CardCreateHandler, e possivelmente mais)

## Passo 1: Ler handlers/payment.py COMPLETO

Entender todas as classes e como usam _get_payment_backend().

## Passo 2: Migrar para pool + BaseHandler

Para cada handler class:
1. Herdar de BaseHandler (WP-3A)
2. Substituir _get_payment_backend() por payment_methods_pool.get_method(identifier)
3. Mover execute logic para execute() method

Após migrar todas:
1. Remover _payment_backend_cache e _get_payment_backend()
2. Remover import de PaymentBackend protocol (não precisa mais)

## Passo 3: Verificar que payment_mock adapter funciona

O MockPaymentBackend em adapters/payment_mock.py precisa herdar de
PaymentMethod (WP-1A) em vez de implementar o Protocol. Se necessário,
adaptar (mas NÃO neste WP se for complexo — criar WP separado).

Se payment_mock já implementa os mesmos métodos (create_intent, capture,
refund), basta mudar a herança. Se não, adaptar a interface.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-3C: notification handler → pool

**Status:** concluído
**Risco:** médio (fallback chain logic)
**Depende de:** WP-1B (pool), WP-3A (BaseHandler)

#### Prompt

```
Execute o WP-3C do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

handlers/notification.py (269 linhas) implementa fallback chain inline
(primary backend → fallbacks from config). Com o pool, a fallback chain
é a ORDEM dos backends no pool (ou no config do canal).

## Passo 1: Ler handlers/notification.py COMPLETO

Entender a fallback chain e como os adapters são chamados.

## Passo 2: Migrar para pool + BaseHandler

1. Herdar de BaseHandler
2. Substituir get_adapter("notification") por notification_pool
3. Fallback chain: iterar notification_pool.get_available() em ordem,
   parar no primeiro que retorne success=True

## Passo 3: Adaptar adapters/notification_*.py

Os adapters (console, email, sms, webhook, whatsapp) precisam herdar
de NotificationBackend (WP-1B). Para cada adapter:
1. Ler o arquivo
2. Adicionar herança de NotificationBackend
3. Garantir que tem identifier e send() com a assinatura correta
4. Adicionar is_available() se necessário (ex: email sem SMTP → False)

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-3D: Eliminar customer handler

**Status:** concluído
**Risco:** baixo
**Depende de:** WP-2B (service já usa pool)

#### Prompt

```
Execute o WP-3D do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

handlers/customer.py (344 linhas) é um handler async para customer
resolution. Mas customer resolution é SYNC — acontece em Flow.on_commit()
via services/customer.ensure(). O handler é redundante.

## Passo 1: Verificar se o handler é realmente redundante

1. Ler handlers/customer.py COMPLETO
2. Grep por CustomerEnsureHandler em todo o projeto
3. Verificar se algum Directive é criado com o topic do customer handler
4. Verificar se flows.py chama customer.ensure() diretamente

Se o handler faz algo que o service NÃO faz (ex: retry, alertas),
avaliar se esse algo deve migrar para o service ou para o flow.

## Passo 2: Se redundante, eliminar

1. Deletar handlers/customer.py
2. Remover registro do handler em settings.py (SHOPMAN_HANDLERS)
3. Remover qualquer import residual

Se NÃO for redundante, PARAR e reportar o que o handler faz de diferente.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-3E: stock handler → simplificar

**Status:** concluído
**Risco:** médio (691 → 428 linhas, delegou para stock_internal adapter)
**Depende de:** WP-3A (BaseHandler)

#### Prompt

```
Execute o WP-3E do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

handlers/stock.py (691 linhas) é o maior handler. Contém:
- StockHoldHandler
- StockCommitHandler
- Bundle expansion logic
- Alternative SKU resolution
- Stock alert checks

O handler já chama Core direto (StockService). A simplificação é:
1. Herdar de BaseHandler
2. Extrair bundle expansion para helper function (se não está no Core)
3. Mover lógica de alertas para _stock_receivers.py ou stock_alerts.py

## Passo 1: Ler handlers/stock.py COMPLETO

Identificar os blocos de lógica e classificar:
- Core logic (deve ficar no handler)
- Helper logic (extrair)
- Dead code (eliminar)

## Passo 2: Migrar para BaseHandler

Cada handler class herda de BaseHandler. execute() contém a lógica.

## Passo 3: Simplificar onde possível

- Bundle expansion: se o Core já faz, remover duplicação
- Alternative SKU: avaliar se é lógica genérica ou instance-specific
- Stock alerts: já estão em stock_alerts.py — remover duplicação

Meta: de 691 → ~300 linhas.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-3F: fiscal/accounting handlers → pool

**Status:** concluído
**Risco:** baixo
**Depende de:** WP-1D (pool), WP-3A (BaseHandler)

#### Prompt

```
Execute o WP-3F do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

handlers/fiscal.py (145 linhas) usa global cache idêntico ao payment.
handlers/accounting.py (91 linhas) é similar.

## Passo 1: Ler ambos os handlers COMPLETO

## Passo 2: Migrar para pool + BaseHandler

fiscal.py:
1. Herdar de BaseHandler
2. Substituir _get_fiscal_backend() por fiscal_pool.get_backend()
3. Remover global cache

accounting.py:
1. Herdar de BaseHandler
2. Avaliar se accounting precisa de pool (ARCH-PLAN dizia "talvez")
   - Se tem UM backend e é simples → manter inline, sem pool
   - Se precisa de pool → criar (mesmo pattern)

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

## Fase 4 — Instance Extraction (7 WPs)

Mover hardcodes e lógica instance-specific para nelson/ e settings.
Independente das Fases 2-3 (pode rodar em paralelo).

---

### WP-4A: Hardcodes → settings

**Status:** concluído
**Risco:** baixo (trocar constantes por shopman_settings.*)
**Depende de:** WP-1G (ShopmanSettings)

#### Prompt

```
Execute o WP-4A do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

~15 hardcodes de instância espalhados pelo código. Migrar para
shopman_settings.* (WP-1G) e configurar valores em nelson settings.

## Passo 1: Inventário

Grep por todos os hardcodes conhecidos:
1. CHANNEL_REF = "web" ou channel_ref = "web" em shopman/web/
2. "43" como DDD em shopman/
3. operator email hardcoded
4. TTLs hardcoded (que não estão no ChannelConfig)
5. Listing refs hardcoded
6. Collection names/icons hardcoded

Para cada hardcode, anotar: arquivo, linha, valor, contexto.

## Passo 2: Substituir por shopman_settings

Para cada hardcode:
1. Se já existe property correspondente em ShopmanSettings → usar
2. Se não existe → adicionar property com default genérico
3. Substituir o hardcode por shopman_settings.PROPERTY_NAME

## Passo 3: Configurar na instance

Em project/settings.py, adicionar os valores de Nelson:
```python
SHOPMAN_STOREFRONT_CHANNEL = "web"
SHOPMAN_DEFAULT_PHONE_DDD = "43"
SHOPMAN_OPERATOR_EMAIL = "..."  # se existir
```

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-4B: Phone normalization → utility único

**Status:** concluído (no-op — já centralizado em shopman.utils.phone.normalize_phone)
**Risco:** baixo

#### Prompt

```
Execute o WP-4B do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Phone normalization acontece em múltiplos lugares com lógicas
potencialmente diferentes. Deve haver UM ponto.

## Passo 1: Inventário

Grep por normalize_phone, _normalize_phone, phone normalization em todo
o projeto (shopman-app/ e shopman-core/).

## Passo 2: Avaliar

Se já existe UM ponto (shopman.utils.phone.normalize_phone) e todos os
callers já o usam → este WP é no-op. Marcar como concluído.

Se há duplicação → unificar no ponto que já existe, usando
shopman_settings.DEFAULT_PHONE_DDD como default.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-4C: Notification templates → nelson/

**Status:** concluído
**Risco:** baixo

#### Prompt

```
Execute o WP-4C do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Templates de notificação (emails, mensagens) devem estar na instance,
não no framework. Shopman fornece a engine; Nelson fornece o conteúdo.

## Passo 1: Inventário

Localizar TODOS os templates de notificação:
1. Templates de email em shopman-app/shopman/templates/
2. Strings inline em adapters/notification_*.py
3. Mensagens hardcoded em handlers/notification.py

## Passo 2: Avaliar escopo

Se templates já estão em nelson/ → no-op.
Se estão em shopman/ mas são genéricos (sem texto em português) → manter.
Se contêm texto específico de Nelson → mover para nelson/templates/.

ATENÇÃO: Não mover templates que são do storefront (web UI) — apenas
templates de notificação (email/SMS/WhatsApp enviados ao cliente).

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-4D: Email adapter → eliminar duplicação

**Status:** concluído
**Risco:** baixo

#### Prompt

```
Execute o WP-4D do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

O adapter de email pode ter duplicação entre funções de módulo e métodos
de classe.

## Passo 1: Ler adapters/notification_email.py COMPLETO (326 linhas)

Identificar:
1. Existe uma classe E funções de módulo que fazem a mesma coisa?
2. Os handlers chamam as funções ou a classe?

## Passo 2: Se houver duplicação, unificar

Manter a classe (para herdar de NotificationBackend no WP-3C).
Remover funções de módulo redundantes.

Se NÃO houver duplicação → no-op. Marcar como concluído.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-4E: Carrier tracking URLs → instance config

**Status:** concluído
**Risco:** baixo

#### Prompt

```
Execute o WP-4E do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

URLs de rastreamento de transportadoras (Correios, Jadlog, etc.) são
lógica de instância, não de framework.

## Passo 1: Localizar

Grep por tracking URL patterns (rastreamento, jadlog, correios, tracking)
em shopman-app/.

## Passo 2: Se hardcoded → mover para settings

Adicionar property em ShopmanSettings:
```python
@property
def CARRIER_TRACKING_URLS(self):
    return getattr(settings, "SHOPMAN_CARRIER_TRACKING_URLS", {})
```

Configurar em nelson settings:
```python
SHOPMAN_CARRIER_TRACKING_URLS = {
    "correios": "https://rastreamento.correios.com.br/?objetos={}",
    ...
}
```

Se NÃO houver hardcodes → no-op.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-4F: apps.py → limpar conditional registration

**Status:** concluído
**Risco:** médio (muda boot sequence)
**Depende de:** WP-1A-1D (pools existem)

#### Prompt

```
Execute o WP-4F do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

apps.py (ShopmanConfig.ready()) registra handlers, modifiers, e faz wiring
de signals. Pode conter conditional imports (if twilio_sid, if manychat_token)
e referências diretas a nelson.

## Passo 1: Ler shopman-app/shopman/apps.py COMPLETO

Identificar:
1. Conditional imports (try/except ImportError, if getattr(settings, ...))
2. Referências diretas a nelson/ code
3. Registration logic (handlers, modifiers, validators)

## Passo 2: Simplificar

O ARCH-PLAN A3 já migrou registro para settings. Verificar se sobrou
conditional logic. Se sim:
1. Remover condicionais — se está no settings, está habilitado
2. Remover referências a nelson/ — instance configura em seu próprio apps.py
3. Manter apenas signal wiring e pool-related setup

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-4G: nelson/resolvers.py — já coberto em WP-2B

Este WP foi absorvido pelo WP-2B.

---

## Fase 5 — Polish (5 WPs)

---

### WP-5A: Índices no banco

**Status:** concluído
**Risco:** baixo

#### Prompt

```
Execute o WP-5A do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Models do shopman-app podem estar sem índices adequados para queries
frequentes.

## Passo 1: Identificar models

Ler shopman-app/shopman/models/ e listar todos os models com seus campos.

## Passo 2: Avaliar índices

Para cada model, verificar:
1. Campos usados em filter/order_by nos views e handlers
2. ForeignKey já tem índice (Django cria automaticamente)
3. Campos de status + timestamp (padrão: Index(["status", "created_at"]))

## Passo 3: Adicionar índices faltantes

Adicionar Meta.indexes onde necessário. Não criar migração ainda
(WP-5B reseta todas).

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-5B: Reset migrações

**Status:** concluído
**Risco:** médio (requer seed funcional)

#### Prompt

```
Execute o WP-5B do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

App novo, sem deploy em produção. Múltiplas migrações podem ser
squashed em uma 0001_initial.py limpa.

## Passo 1: Verificar estado

1. Listar todas as migrações em shopman-app/shopman/migrations/
2. Confirmar que não há deploy em produção (é app novo)

## Passo 2: Reset

1. Deletar todas as migrações EXCETO __init__.py
2. Rodar `python manage.py makemigrations shopman`
3. Confirmar que gera uma 0001_initial.py limpa
4. Rodar `make test-shopman-app` para confirmar

## Verificação
- `make migrate` (em banco limpo)
- `make test-shopman-app`
- `make seed` (se existe)
```

---

### WP-5C: Web: parametrizar views

**Status:** concluído
**Risco:** baixo
**Depende de:** WP-1G (ShopmanSettings), WP-4A (hardcodes migrados)

#### Prompt

```
Execute o WP-5C do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Views do storefront podem ter hardcodes residuais após WP-4A.

## Passo 1: Grep final

Buscar em shopman-app/shopman/web/ por:
1. String literals que parecem instance-specific (nomes, refs, etc.)
2. Constantes que deveriam ser shopman_settings.*

## Passo 2: Parametrizar residuais

Substituir por shopman_settings ou por contexto do template.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

### WP-5D: Eliminar testes mortos

**Status:** concluído
**Risco:** baixo

#### Prompt

```
Execute o WP-5D do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Após as refatorações, pode haver testes que testam código deletado
(pricing.resolve, production.*, customer handler, etc.).

## Passo 1: Identificar

Rodar `make test-shopman-app` e verificar:
1. Testes que falham por import removido
2. Testes que testam funções que não existem mais

## Passo 2: Limpar

1. Deletar testes de código removido
2. Atualizar testes que precisam de ajuste (imports, mocks)
3. Adicionar testes para os pools (se não existem)

## Verificação
- `make test-shopman-app` (todos passando)
- `make lint`
```

---

### WP-5E: Testes de integração por flow

**Status:** concluído
**Risco:** baixo

#### Prompt

```
Execute o WP-5E do REFACTOR-SHOPMAN-PLAN.md.

## Contexto

Após todas as refatorações, garantir que os flows end-to-end funcionam
com os pools.

## Passo 1: Verificar testes existentes

Ler shopman-app/shopman/tests/integration/ e shopman-app/shopman/tests/test_flows.py.

## Passo 2: Avaliar cobertura

Para cada flow (POS, Web, WhatsApp, iFood):
- Existe teste que exercita o flow completo (commit → confirm → pay → fulfill)?
- O teste usa os pools (payment_methods_pool, notification_pool, etc.)?

## Passo 3: Adicionar testes faltantes

Se faltam testes para algum flow, adicionar. Focar no happy path.
Usar payment_mock e notification_console como backends de teste.

## Verificação
- `make test-shopman-app`
```

---

## Plano de Execução (resumo)

```
Fase 1 — Pools + Alicerce                          7 WPs
  WP-1E  exceptions.py     ShopmanError           ■ independente
  WP-1G  conf.py            ShopmanSettings        ■ independente
  WP-1F  directives.py      queue() helper         ■ independente
  WP-1A  payment.py         PaymentMethod + Pool   ■ independente
  WP-1B  notification.py    NotificationBackend    ■ independente
  WP-1C  customer.py        CustomerResolver       ■ independente
  WP-1D  fiscal.py          FiscalBackend          ■ independente
  → Todos podem ser executados em paralelo (criam arquivos novos)

Fase 2 — Services                                  5 WPs
  WP-2A  Eliminar pricing/production               ■ independente
  WP-2B  customer → pool                           ← WP-1C
  WP-2C  notification/loyalty/fiscal → queue()     ← WP-1F
  WP-2D  payment → pool                            ← WP-1A
  WP-2E  stock → Core direto                       ■ independente

Fase 3 — Handlers                                  6 WPs
  WP-3A  BaseHandler                               ← Fase 1
  WP-3B  payment handlers → pool                   ← WP-3A + WP-1A
  WP-3C  notification handler → pool               ← WP-3A + WP-1B
  WP-3D  Eliminar customer handler                 ← WP-2B
  WP-3E  stock handler → simplificar               ← WP-3A
  WP-3F  fiscal/accounting → pool                  ← WP-3A + WP-1D

Fase 4 — Instance Extraction                       6 WPs
  WP-4A  Hardcodes → settings                      ← WP-1G
  WP-4B  Phone normalization                       ■ independente
  WP-4C  Notification templates → nelson/          ■ independente
  WP-4D  Email adapter duplicação                  ■ independente
  WP-4E  Carrier tracking URLs                     ← WP-1G
  WP-4F  apps.py cleanup                           ← Fase 1

Fase 5 — Polish                                    5 WPs
  WP-5A  Índices                                   ■ independente
  WP-5B  Reset migrações                           ← tudo antes
  WP-5C  Web parametrizar                          ← WP-4A
  WP-5D  Eliminar testes mortos                    ← Fases 2-3
  WP-5E  Testes de integração                      ← tudo antes
```

**29 WPs. 5 fases. ~22 WPs únicos (WP-4G absorvido em WP-2B).**

---

## Métricas

| Métrica | Antes | Meta |
|---------|-------|------|
| Extension points (adapters/protocols) | ~10 implícitos | 4 explícitos (pools) |
| services/ | 14 módulos, 1.150 linhas | 7 módulos, ~400 linhas |
| handlers/ | 3.612 linhas | ~1.600 linhas |
| customer.py (service) | 319 linhas, if/elif | ~50 linhas, pool delegation |
| Globals mutáveis | 3 | 0 (pools com reset) |
| Hardcodes de instance | ~15 | 0 |
| Error handling patterns | 3 | 1 (ShopmanError + BaseHandler) |
| Directive.objects.create() espalhados | 5+ locais | 1 (directives.queue()) |
