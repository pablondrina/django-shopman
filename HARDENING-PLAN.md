# HARDENING-PLAN.md — Reestruturação e Hardening do Django Shopman

Plano consolidado após 7 rodadas de análise, desconstrução e stress test.
Projeto novo, sem legado. Fazer certo desde o início.

---

## Princípio Orientador

O **Core** oferece capacidades genéricas (o que PODE ser feito).
A **Loja** define quem somos e nossas regras de negócio.
Os **Canais** definem como vendemos — estratégias, mecânicas, interfaces.

Toda configuração segue a **cascata**: Canal → Loja → Defaults.
Identificadores textuais são `ref`, não `code`. Exceção única: `Product.sku`.

---

## WP-H0: Reestruturação Completa

### Estrutura Final

```
shopman-app/
├── project/
│   ├── settings.py          # Plumbing Django PURO (~80 linhas)
│   ├── urls.py
│   └── wsgi.py
│
├── shop/                    # QUEM SOMOS — identidade + regras
│   ├── models.py            # Shop singleton
│   ├── admin.py             # Admin da loja (Unfold branding aqui)
│   ├── validators.py        # Validators do negócio
│   ├── modifiers.py         # Modifiers do negócio
│   ├── context_processors.py
│   ├── management/commands/seed.py
│   └── apps.py
│
├── channels/                # COMO VENDEMOS
│   ├── config.py            # ChannelConfig (7 aspectos + cascata)
│   ├── presets.py           # Templates de canal (pos, remote, marketplace)
│   ├── protocols.py         # Contratos de backend
│   ├── hooks.py             # Signal dispatch → pipeline
│   ├── setup.py             # Registro centralizado
│   │
│   ├── handlers/            # Passos do pipeline
│   │   ├── stock.py         # StockHoldHandler, StockCommitHandler, StockCheck
│   │   ├── customer.py      # CustomerEnsureHandler
│   │   ├── confirmation.py  # ConfirmationTimeoutHandler
│   │   ├── notification.py  # NotificationSendHandler + routing
│   │   ├── payment.py       # PixGenerate, Capture, Refund, Timeout
│   │   ├── pricing.py       # ItemPricingModifier, SessionTotalModifier
│   │   ├── fiscal.py        # NFCeEmitHandler, NFCeCancelHandler
│   │   ├── accounting.py    # PurchaseToPayableHandler
│   │   ├── fulfillment.py   # FulfillmentCreateHandler
│   │   └── returns.py       # ReturnHandler + ReturnService
│   │
│   ├── backends/            # Pontes para Core e externos
│   │   ├── stock.py         # StockingBackend → shopman.stocking
│   │   ├── customer.py      # CustomersBackend → shopman.customers
│   │   ├── pricing.py       # OfferingBackend → shopman.offering
│   │   ├── payment_mock.py  # MockPaymentBackend
│   │   ├── payment_efi.py   # EfiPaymentBackend
│   │   ├── notification_console.py
│   │   └── notification_manychat.py
│   │
│   ├── web/                 # Interface web
│   │   ├── views/
│   │   ├── templates/
│   │   ├── static/
│   │   ├── cart.py
│   │   └── apps.py
│   │
│   └── apps.py              # ChannelsConfig
│
└── tests/
```

INSTALLED_APPS: `"shop"`, `"channels"`, `"channels.web"` (+ core apps + django + third-party).

---

### ChannelConfig — O Coração

7 aspectos. Cada um responde a UMA pergunta.

```python
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class ChannelConfig:
    """
    Configuração completa de um canal de venda.

    confirmation  — como o pedido é aceito?
    payment       — como o cliente paga?
    stock         — comportamento de reserva de estoque
    pipeline      — o que acontece em cada fase do pedido?
    notifications — por onde avisamos?
    rules         — quais validators/modifiers ativar?
    flow          — como o pedido transita entre status?
    """

    # ── 1. Confirmação ──

    @dataclass
    class Confirmation:
        mode: str = "immediate"
        # "immediate"  — auto-confirma na criação
        # "optimistic" — auto-confirma após timeout se operador não cancela
        # "manual"     — aguarda aprovação explícita do operador
        timeout_minutes: int = 5  # só para mode=optimistic

    # ── 2. Pagamento ──

    @dataclass
    class Payment:
        method: str = "counter"
        # "counter"  — no caixa/entrega
        # "pix"      — PIX com QR code
        # "external" — já pago (marketplace)
        timeout_minutes: int = 15  # só para method=pix
        # Não existe require_prepayment — o pipeline expressa isso:
        # pix.generate em on_confirmed + stock.commit em on_payment_confirmed = prepayment
        # stock.commit em on_confirmed (sem esperar pagamento) = pós-pagamento

    # ── 3. Estoque ──

    @dataclass
    class Stock:
        hold_ttl_minutes: int | None = None  # None = sem expiração
        safety_margin: int = 0
        # Verificação pré-commit é feita via Check (rules.checks: ["stock"])
        # Check = par directive+validator — ver seção Checks abaixo

    # ── 4. Pipeline ──

    @dataclass
    class Pipeline:
        """O que acontece em cada fase do ciclo de vida.

        Cada fase é uma lista de directive topics.
        Notação "topic:template" para notificações com template.
        Fases mapeiam 1:1 com Order.Status + eventos especiais.
        """
        on_commit: list[str] = field(default_factory=list)
        on_confirmed: list[str] = field(default_factory=list)
        on_processing: list[str] = field(default_factory=list)
        on_ready: list[str] = field(default_factory=list)
        on_dispatched: list[str] = field(default_factory=list)
        on_delivered: list[str] = field(default_factory=list)
        on_completed: list[str] = field(default_factory=list)
        on_cancelled: list[str] = field(default_factory=list)
        on_returned: list[str] = field(default_factory=list)
        # Evento especial (não é status — vem de webhook de pagamento)
        on_payment_confirmed: list[str] = field(default_factory=list)

    # ── 5. Notificações ──

    @dataclass
    class Notifications:
        backend: str = "console"
        # "console" | "email" | "manychat" | "sms" | "webhook" | "none"
        fallback: str | None = None
        routing: dict[str, str] | None = None
        # Override por template: {"payment_reminder": "manychat", ...}
        # Se ausente, usa backend para tudo

    # ── 6. Regras ──

    @dataclass
    class Rules:
        """Validators, modifiers e checks ativos neste canal.

        Herança via cascata (deep_merge no nível de dict):
        - Chave ausente = herda do nível anterior
        - Lista explícita = sobreescreve
        - Lista vazia [] = desativa

        Três categorias:
        - validators: gate puro (sem IO, sem mutação). Ex: business_hours, min_order
        - modifiers: transformação determinística (sem IO). Ex: happy_hour, employee_discount
        - checks: par directive+validator para verificações pré-commit com IO.
          Ex: "stock" → cria stock.hold durante modify, valida frescor no commit.
        """
        validators: list[str] = field(default_factory=list)
        modifiers: list[str] = field(default_factory=list)
        checks: list[str] = field(default_factory=list)

    # ── 7. Fluxo ──

    @dataclass
    class Flow:
        """Customização do fluxo de status.
        Se ausente, usa Order.DEFAULT_TRANSITIONS.
        """
        transitions: dict[str, list[str]] | None = None
        terminal_statuses: list[str] | None = None
        auto_transitions: dict[str, str] | None = None

    # ── Campos ──

    confirmation: Confirmation = field(default_factory=Confirmation)
    payment: Payment = field(default_factory=Payment)
    stock: Stock = field(default_factory=Stock)
    pipeline: Pipeline = field(default_factory=Pipeline)
    notifications: Notifications = field(default_factory=Notifications)
    rules: Rules = field(default_factory=Rules)
    flow: Flow = field(default_factory=Flow)

    # ── Serialização ──

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ChannelConfig:
        return cls(
            confirmation=cls.Confirmation(**data.get("confirmation", {})),
            payment=cls.Payment(**data.get("payment", {})),
            stock=cls.Stock(**data.get("stock", {})),
            pipeline=cls.Pipeline(**{
                k: v for k, v in data.get("pipeline", {}).items()
                if k.startswith("on_")
            }),
            notifications=cls.Notifications(**data.get("notifications", {})),
            rules=cls.Rules(**data.get("rules", {})),
            flow=cls.Flow(**{
                k: v for k, v in data.get("flow", {}).items()
                if v is not None
            }),
        )

    @classmethod
    def defaults(cls) -> dict:
        return cls().to_dict()

    # ── Cascata ──

    @classmethod
    def effective(cls, channel) -> ChannelConfig:
        """
        Configuração efetiva: canal ← loja ← defaults.

        Chave ausente no override = herda.
        Chave presente (mesmo null) = sobreescreve.
        """
        from shop.models import Shop

        base = cls.defaults()
        shop = Shop.load()
        if shop and shop.defaults:
            base = deep_merge(base, shop.defaults)
        if channel.config:
            base = deep_merge(base, channel.config)
        return cls.from_dict(base)

    # ── Validação ──

    def validate(self):
        if self.confirmation.mode not in ("immediate", "optimistic", "manual"):
            raise ValueError(f"confirmation.mode inválido: {self.confirmation.mode}")
        if self.confirmation.mode == "optimistic" and self.confirmation.timeout_minutes <= 0:
            raise ValueError("timeout_minutes deve ser > 0 para mode=optimistic")
        if self.payment.method not in ("counter", "pix", "external"):
            raise ValueError(f"payment.method inválido: {self.payment.method}")
        if self.payment.method == "pix" and self.payment.timeout_minutes <= 0:
            raise ValueError("timeout_minutes deve ser > 0 para method=pix")


def deep_merge(base: dict, override: dict) -> dict:
    """
    Merge profundo: override sobreescreve base.

    - Chave ausente no override = herda de base
    - Chave presente (mesmo None) = sobreescreve
    - dict + dict = merge recursivo
    - list sobreescreve (não concatena)
    """
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

---

### Presets

```python
# channels/presets.py

from channels.config import ChannelConfig

def pos() -> dict:
    """Balcão — operador presente, pagamento no caixa."""
    return ChannelConfig(
        confirmation=ChannelConfig.Confirmation(mode="immediate"),
        payment=ChannelConfig.Payment(method="counter"),
        stock=ChannelConfig.Stock(hold_ttl_minutes=5),
        pipeline=ChannelConfig.Pipeline(
            on_commit=["customer.ensure"],
            on_confirmed=["stock.commit", "notification.send:order_confirmed"],
            on_cancelled=["notification.send:order_cancelled"],
        ),
        notifications=ChannelConfig.Notifications(backend="console"),
        rules=ChannelConfig.Rules(
            validators=["business_hours"],
            modifiers=["employee_discount"],
        ),
    ).to_dict()


def remote() -> dict:
    """Remoto — e-commerce, WhatsApp. PIX, confirmação otimista."""
    return ChannelConfig(
        confirmation=ChannelConfig.Confirmation(mode="optimistic", timeout_minutes=10),
        payment=ChannelConfig.Payment(method="pix", timeout_minutes=15),
        stock=ChannelConfig.Stock(hold_ttl_minutes=30),
        pipeline=ChannelConfig.Pipeline(
            on_commit=["customer.ensure", "stock.hold"],
            on_confirmed=["pix.generate", "notification.send:order_confirmed"],
            on_payment_confirmed=["stock.commit", "notification.send:payment_confirmed"],
            on_ready=["notification.send:order_ready"],
            on_cancelled=["stock.release", "notification.send:order_cancelled"],
        ),
        notifications=ChannelConfig.Notifications(
            backend="email",
            routing={"payment_reminder": "manychat"},
        ),
        rules=ChannelConfig.Rules(
            validators=["business_hours", "min_order"],
            modifiers=["happy_hour"],
            checks=["stock"],
        ),
    ).to_dict()


def marketplace() -> dict:
    """Marketplace — iFood, Rappi. Já pago, já confirmado."""
    return ChannelConfig(
        confirmation=ChannelConfig.Confirmation(mode="immediate"),
        payment=ChannelConfig.Payment(method="external"),
        pipeline=ChannelConfig.Pipeline(
            on_commit=["customer.ensure"],
            on_confirmed=["stock.commit"],
        ),
        notifications=ChannelConfig.Notifications(backend="none"),
        rules=ChannelConfig.Rules(validators=[], modifiers=[]),
    ).to_dict()
```

---

### Checks — par directive + validator

Conceito novo no Registry que resolve a dualidade preparação (IO) + validação (gate puro)
sem violar o princípio de que Validators não fazem IO.

**Princípios preservados:**

| Conceito | Faz IO? | Muta estado? | Quando roda |
|---|---|---|---|
| Validator | Não | Não | Commit (gate puro) |
| Modifier | Não | Sim (session) | Modify (transformação) |
| DirectiveHandler | Sim | Sim | Pós-transição (async) |
| **Check** | topic: sim / validate: não | Não | Modify (directive) + Commit (validação) |

**Registry:**

```python
# ordering/registry.py — novo Protocol

@runtime_checkable
class Check(Protocol):
    """
    Par directive + validator para verificações pré-commit.

    O Check DECLARA o par. Não faz IO nem valida diretamente.
    O ModifyService cria a directive (topic). O CommitService chama validate().
    """
    code: str
    topic: str  # directive topic para a preparação (IO)

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        """Gate puro — valida o resultado da preparação. Sem IO."""
        ...
```

```python
# _Registry ganha:
self._checks: dict[str, Check] = {}

def register_check(self, check: Check) -> None: ...
def get_check(self, code: str) -> Check | None: ...
```

**Implementação (stock):**

```python
# channels/handlers/stock.py

class StockCheck:
    """Check de estoque: reserva durante modify, valida no commit."""
    code = "stock"
    topic = "stock.hold"  # directive criada pelo ModifyService

    def validate(self, *, channel, session, ctx):
        """Gate puro: verifica que o resultado do stock.hold está fresco."""
        checks = session.data.get("checks", {})
        stock_check = checks.get("stock")
        if not stock_check:
            raise ValidationError(code="missing_check", message="Stock check obrigatório")
        if stock_check.get("rev") != session.rev:
            raise ValidationError(code="stale_check", message="Stock check desatualizado")
```

**ModifyService — cria directives dos checks ativos:**

```python
# ordering/services/modify.py — trecho
config = ChannelConfig.effective(channel)

for check_code in config.rules.checks:
    check = registry.get_check(check_code)
    if check:
        Directive.objects.create(topic=check.topic, payload={
            "session_key": session.session_key,
            "channel_ref": channel.ref,
            "rev": session.rev,
            "items": session.items,
        })
```

**CommitService — valida checks ativos:**

```python
# ordering/services/commit.py — trecho
config = ChannelConfig.effective(channel)

for check_code in config.rules.checks:
    check = registry.get_check(check_code)
    if check:
        check.validate(channel=channel, session=session, ctx=ctx)
```

**Registro centralizado:**

```python
# channels/setup.py
from channels.handlers.stock import StockCheck
registry.register_check(StockCheck())
```

---

### Channel model — listing_ref

```python
# ordering/models/channel.py — novo campo
class Channel(models.Model):
    ref = models.CharField(...)
    name = models.CharField(...)
    listing_ref = models.CharField(
        "listagem", max_length=50, blank=True,
        help_text="Ref da Listing que serve como catálogo deste canal",
    )
    config = models.JSONField(...)
```

Listing.ref no Core (offering) renomeado para Listing.ref (entra no WP-H0b).

### Pricing cascade (canal → grupo → base)

```python
# channels/backends/pricing.py

class OfferingBackend:
    """Resolve preço pela cascata: grupo do cliente → listing do canal → preço base."""

    def get_price(self, sku: str, channel, customer=None) -> int:
        # 1. Preço do grupo do cliente (se identificado e tem grupo com listing)
        if customer and customer.group and customer.group.listing_ref:
            item = self._get_listing_item(customer.group.listing_ref, sku)
            if item and item.is_available:
                return item.price_q

        # 2. Preço do canal (via listing do canal)
        if channel.listing_ref:
            item = self._get_listing_item(channel.listing_ref, sku)
            if item and item.is_available:
                return item.price_q

        # 3. Preço base do produto
        from shopman.offering.models import Product
        product = Product.objects.get(sku=sku)
        return product.base_price_q

    def _get_listing_item(self, listing_ref, sku):
        from shopman.offering.models import ListingItem
        return ListingItem.objects.filter(
            listing__ref=listing_ref,
            product__sku=sku,
            is_published=True,
        ).first()
```

### Catálogo do canal com disponibilidade em dois níveis

```python
# channels/web/views/catalog.py

def get_channel_products(channel):
    """Produtos disponíveis neste canal. Dois gates: global + canal."""
    if channel.listing_ref:
        return Product.objects.filter(
            # Gate GLOBAL (produto ativo no catálogo geral)
            is_published=True,
            is_available=True,
            # Gate CANAL (produto ativo nesta listing)
            listing_items__listing__ref=channel.listing_ref,
            listing_items__is_published=True,
            listing_items__is_available=True,
        ).distinct()
    else:
        return Product.objects.active()
```

---

### Hooks como dispatcher genérico

```python
# channels/hooks.py

from datetime import timedelta
from django.utils import timezone
from channels.config import ChannelConfig
from shopman.ordering.models import Directive, Order


def on_order_lifecycle(sender, order, event_type, actor, **kwargs):
    """Dispatcher genérico: lê pipeline do canal, cria directives."""
    if event_type == "created":
        _on_order_created(order)
        return

    if event_type != "status_changed":
        return

    config = ChannelConfig.effective(order.channel)
    phase = f"on_{order.status}"
    topics = getattr(config.pipeline, phase, [])

    for entry in topics:
        topic, _, template = entry.partition(":")
        payload = {"order_ref": order.ref, "channel_ref": order.channel.ref}
        if template:
            payload["template"] = template
        Directive.objects.create(topic=topic, payload=payload)


def _on_order_created(order):
    """Confirmação: imediata, otimista, ou manual."""
    config = ChannelConfig.effective(order.channel)

    if config.confirmation.mode == "optimistic":
        expires_at = timezone.now() + timedelta(minutes=config.confirmation.timeout_minutes)
        Directive.objects.create(
            topic="confirmation.timeout",
            payload={"order_ref": order.ref, "expires_at": expires_at.isoformat()},
            available_at=expires_at,
        )
    elif config.confirmation.mode == "immediate":
        order.transition_status(Order.Status.CONFIRMED, actor="auto_confirm")
    # mode == "manual": order fica em NEW até aprovação explícita


def on_payment_confirmed(order):
    """Chamado pelo webhook de pagamento."""
    config = ChannelConfig.effective(order.channel)

    # Auto-transition se configurada
    target = (config.flow.auto_transitions or {}).get("on_payment_confirm")
    if target and order.can_transition_to(target):
        order.transition_status(target, actor="payment.webhook")

    # Pipeline
    for entry in config.pipeline.on_payment_confirmed:
        topic, _, template = entry.partition(":")
        payload = {"order_ref": order.ref, "channel_ref": order.channel.ref}
        if template:
            payload["template"] = template
        Directive.objects.create(topic=topic, payload=payload)
```

---

### Shop model

```python
# shop/models.py

class Shop(models.Model):
    """O estabelecimento. Singleton."""

    # ── Identidade ──
    name = models.CharField("nome fantasia", max_length=200)
    legal_name = models.CharField("razão social", max_length=200, blank=True)
    document = models.CharField("CNPJ/CPF", max_length=20, blank=True)

    # ── Localização ──
    address = models.TextField("endereço", blank=True)
    city = models.CharField("cidade", max_length=100, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
    postal_code = models.CharField("CEP", max_length=10, blank=True)
    phone = models.CharField("telefone", max_length=20, blank=True)
    default_ddd = models.CharField("DDD padrão", max_length=4, default="11")

    # ── Operação ──
    currency = models.CharField("moeda", max_length=3, default="BRL")
    timezone = models.CharField("fuso horário", max_length=50, default="America/Sao_Paulo")
    opening_hours = models.JSONField("horários", default=dict, blank=True)

    # ── Branding (substitui StorefrontConfig) ──
    brand_name = models.CharField("marca", max_length=100, blank=True)
    short_name = models.CharField("nome curto (PWA)", max_length=30, blank=True)
    tagline = models.CharField("tagline", max_length=200, blank=True)
    primary_color = models.CharField("cor primária", max_length=7, default="#9E833E")
    logo_url = models.URLField("logo", max_length=500, blank=True)

    # ── Redes e contatos ──
    website = models.URLField("site", blank=True)
    instagram = models.CharField("Instagram", max_length=100, blank=True)
    whatsapp = models.CharField("WhatsApp", max_length=20, blank=True)

    # ── Defaults de negócio (cascata: canal ← AQUI ← hardcoded) ──
    defaults = models.JSONField(
        "configurações padrão", default=dict, blank=True,
        help_text="Mesmo schema do ChannelConfig. Canais herdam se não sobreescreverem.",
    )

    class Meta:
        verbose_name = "loja"
        verbose_name_plural = "loja"

    def __str__(self):
        return self.name

    @classmethod
    def load(cls):
        return cls.objects.first()

    def clean(self):
        if self.defaults:
            from channels.config import ChannelConfig
            try:
                ChannelConfig.from_dict(self.defaults)
            except (TypeError, ValueError) as e:
                from django.core.exceptions import ValidationError
                raise ValidationError({"defaults": str(e)})
```

---

## WP-H0b: Renames no Core

**Apps:**
- `customers` → `customers` (app_label: `customers`)
- `auth` → `auth` (app_label: `shopman_auth`)

**Campos:**
- `Listing.ref` → `Listing.ref`
- `CustomerGroup.listing_ref` → `CustomerGroup.listing_ref`
- Qualquer outro `*_code` que seja identificador textual → `*_ref`

**Backends (nomes de classe):**
- `StockmanBackend` → `StockingBackend`
- `GuestmanAdapter` → `CustomersBackend`
- `OffermanAdapter` → `OfferingBackend`

Deletar migrations antigas, criar 0001_initial limpa. Find-replace global.

---

## WP-H1: Order — Integridade Garantida pelo save()

(Sem alteração — side effects mecânicos no save)

---

## WP-H2: Session Items — Comportamento Explícito

(Sem alteração — items read-only, update_items explícito)

---

## WP-H3: Directives — Processamento Pós-Transação

(Sem alteração — transaction.on_commit)

---

## WP-H5: Segurança Básica

(Sem alteração — IsAuthenticated default, AllowAny explícito, security headers)

---

## Novo Core App: shopman.payments

### Diagnóstico

Pagamento hoje é JSON blob em Order.data["payment"]. Não é queryable,
não tem audit trail, não suporta pagamento parcial/múltiplo.

### Models

```python
class PaymentIntent(models.Model):
    """Intenção de pagamento."""
    ref = models.CharField(unique=True, max_length=64)
    order_ref = models.CharField(max_length=64, db_index=True)  # string, não FK
    method = models.CharField(max_length=20)  # pix, counter, card, external
    status = models.CharField(max_length=20)
    # pending | authorized | captured | failed | cancelled | refunded
    amount_q = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="BRL")
    gateway = models.CharField(max_length=50, blank=True)
    gateway_id = models.CharField(max_length=200, blank=True)
    gateway_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    authorized_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)


class PaymentTransaction(models.Model):
    """Movimentação financeira."""
    intent = models.ForeignKey(PaymentIntent, on_delete=models.PROTECT, related_name="transactions")
    type = models.CharField(max_length=20)  # capture, refund, chargeback
    amount_q = models.BigIntegerField()
    gateway_id = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

Agnóstico: usa order_ref (string), não FK. INSTALLED_APPS ganha `"shopman.payments"`.

---

## Features Pipeline (pós-hardening)

### WP-F1: Produção planejada no checkout
- StockHoldHandler respeita Product.availability_policy
- planned_ok: aceita Quants com target_date futura
- demand_ok: cria demand hold → pode disparar WorkOrder

### WP-F2: Keywords para alternativas
- Quando stock.hold falha, buscar produtos com keywords similares (taggit)
- Retornar como alternatives no resultado do check
- Storefront: "Croissant indisponível. Que tal Pain au Chocolat?"

### WP-F3: Auth expandido
- Múltiplos emails/phones por customer (ContactPoint já existe)
- Social login via providers expandidos (Instagram, Google)
- Verificação por canal: OTP SMS, OTP WhatsApp, email link
- Inspiração: Django Allauth pattern, expandido para phones/WhatsApp

### WP-F4: Stock alerts
- Handler stock.alert disparado por signal do stocking
- Quando Quant cai abaixo de StockAlert.min_quantity → notifica operador

---

## Ordem de Execução

```
WP-H0a (shop/)            → fundação: Shop model + absorver StorefrontConfig + nelson
WP-H0b (renames core)     → customers→customers, auth→auth, Listing.ref→ref
WP-H0c (channels/)        → ChannelConfig + presets + handlers + backends + hooks
WP-H0d (integrações)      → listing_ref, pricing cascade, Check, bundle, fulfillment, limpeza
    │
    ├── WP-H1 (Order save)            ─┐
    ├── WP-H2 (Session items)          ├── independentes
    ├── WP-H5 (Segurança)             ─┘
    │   shopman.payments (novo core)   ─┘
    │
    WP-H3 (Directive on_commit)        depende de H1
    │
    WP-F1..F4 (features)               pós-hardening
```

---

## Prompts de Execução

Cada prompt é auto-contido: uma sessão nova lê o HARDENING-PLAN.md e executa.

### WP-H0a — Shop
```
Execute WP-H0a do HARDENING-PLAN.md: Criar app shop/.

Contexto: Projeto novo, sem legado. Leia HARDENING-PLAN.md seção WP-H0 para
entender a estrutura final (shop/ = identidade + regras, channels/ = mecânicas).

Este WP cria APENAS o shop/. Channels/ vem no WP-H0c.

Passos:
1. Crie shopman-app/shop/ como Django app (apps.py, __init__.py)
2. Crie Shop model singleton conforme HARDENING-PLAN.md (identidade, localização,
   operação, branding, redes, defaults JSONField)
3. Crie shop/admin.py com Unfold — mova o branding do settings.py UNFOLD para cá
   (SITE_TITLE via callable lendo Shop.name, TABS e SIDEBAR aqui)
4. Crie shop/context_processors.py (injeta Shop nos templates)
5. Migre nelson/validators.py → shop/validators.py (BusinessHoursValidator, MinimumOrderValidator)
6. Migre nelson/modifiers.py → shop/modifiers.py (EmployeeDiscountModifier, HappyHourModifier)
7. Migre nelson/management/commands/seed_nelson.py → shop/management/commands/seed.py
8. Atualize channels/web/ para ler do Shop em vez de StorefrontConfig
   (context_processors, templates que usam storefront_config)
9. Adicione "shop" ao INSTALLED_APPS
10. Crie migration para Shop
11. Rode make test — todos devem passar (shop/ coexiste com a estrutura antiga por agora)
12. Rode make lint
```

### WP-H0b — Renames Core
```
Execute WP-H0b do HARDENING-PLAN.md: Renames no Core.

Contexto: Projeto novo, migrações serão resetadas. Zero impacto em banco.

Renames:
1. shopman.customers → shopman.customers
   - Renomear pasta: shopman-core/customers/ → shopman-core/customers/
   - Renomear namespace interno: shopman/customers/ → shopman/customers/
   - app_label nos Meta de TODOS os models → "customers"
   - pyproject.toml: nome do pacote
   - Deletar TODAS as migrations, criar 0001_initial limpa

2. shopman.auth → shopman.auth
   - Renomear pasta: shopman-core/auth/ → shopman-core/auth/
   - Renomear namespace: shopman/auth/ → shopman/auth/
   - app_label → "shopman_auth" (evitar colisão com django.contrib.auth)
   - pyproject.toml, migrations idem

3. Campos:
   - Listing.ref → Listing.ref (offering)
   - CustomerGroup.listing_ref → CustomerGroup.listing_ref

4. Find-replace global em TODOS os imports (core + app + tests + docs)
5. Atualizar CLAUDE.md, docs/, glossário com novos nomes
6. Atualizar INSTALLED_APPS em settings.py
7. Rode make test — TODOS devem passar
8. Rode make lint
```

### WP-H0c — Channels
```
Execute WP-H0c do HARDENING-PLAN.md: Criar infra channels/.

Contexto: shop/ já existe (WP-H0a). Leia HARDENING-PLAN.md seções ChannelConfig,
Presets, Checks, Hooks, Pricing cascade, Catálogo.

Este WP cria a infra de channels/ e migra handlers/backends dos 10 mini-apps.
NÃO remove os mini-apps ainda (isso é WP-H0d).

Passos:
1. Crie channels/config.py com ChannelConfig dataclass COMPLETO conforme o plano
   (7 aspectos, from_dict, to_dict, defaults, effective, validate, deep_merge)
2. Crie channels/presets.py (pos, remote, marketplace) usando ChannelConfig
3. Crie channels/protocols.py consolidando todos os Protocols dos mini-apps
   (StockBackend, PaymentBackend, CustomerBackend, PricingBackend, etc.)
4. Crie channels/handlers/ migrando handlers dos mini-apps:
   - shopman/inventory/handlers.py → channels/handlers/stock.py
   - shopman/identification/handlers.py → channels/handlers/customer.py
   - shopman/confirmation/handlers.py → channels/handlers/confirmation.py
   - shopman/notifications/handlers.py → channels/handlers/notification.py
   - shopman/payment/handlers.py → channels/handlers/payment.py
   - shopman/pricing/modifiers.py → channels/handlers/pricing.py
   - shopman/fiscal/handlers.py → channels/handlers/fiscal.py
   - shopman/accounting/handlers.py → channels/handlers/accounting.py
   - shopman/returns/ → channels/handlers/returns.py
   - NOVO: channels/handlers/fulfillment.py (FulfillmentCreateHandler)
   - channels/handlers/stock.py inclui StockCheck (Check protocol)
5. Crie channels/backends/ migrando adapters:
   - Renomear classes: StockmanBackend→StockingBackend, etc.
6. Crie channels/setup.py (registro centralizado de TODOS handlers/backends/checks)
7. Crie channels/hooks.py (dispatcher genérico conforme plano — ~60 linhas)
8. Crie channels/apps.py (ChannelsConfig que chama setup.register_all em ready())
9. Adicione Check protocol ao ordering/registry.py (register_check, get_check)
10. Channel.listing_ref: adicione campo ao Channel model (ordering core)
11. Rode make test — testes devem passar (pode haver falhas de import que precisam ajuste)
12. Rode make lint
```

### WP-H0d — Integrações e Limpeza
```
Execute WP-H0d do HARDENING-PLAN.md: Integrações + Limpeza.

Contexto: shop/ e channels/ existem (H0a, H0c concluídos).

FASE 1 — Integrações:
1. PricingBackend com cascata: grupo.listing_ref → channel.listing_ref → base_price_q
   (conforme código no HARDENING-PLAN.md seção "Pricing cascade")
2. Catálogo filtra por listing em 2 níveis: global + canal
   (conforme código no HARDENING-PLAN.md seção "Catálogo do canal")
3. Bundle explosion no StockHoldHandler: ao reservar bundle, explodir em componentes
4. CommitService: ler pipeline.on_commit via ChannelConfig.effective()
5. CommitService: validar checks via ChannelConfig.effective().rules.checks
6. ModifyService: criar directives dos checks ativos (check.topic)
7. ModifyService: aplicar modifiers de ChannelConfig.effective().rules.modifiers
8. ModifyService: rodar validators de ChannelConfig.effective().rules.validators

FASE 2 — Limpeza:
9. INSTALLED_APPS: remover as 11 entradas antigas, manter shop + channels + channels.web
10. settings.py: tornar plumbing puro (remover UNFOLD branding/tabs/sidebar, CONFIRMATION_FLOW)
11. Remover COMPLETAMENTE:
    - shopman-app/shopman/inventory/
    - shopman-app/shopman/identification/
    - shopman-app/shopman/confirmation/
    - shopman-app/shopman/notifications/
    - shopman-app/shopman/payment/
    - shopman-app/shopman/pricing/
    - shopman-app/shopman/accounting/
    - shopman-app/shopman/fiscal/
    - shopman-app/shopman/returns/
    - shopman-app/shopman/webhook/
    - shopman-app/shopman/orchestration.py
    - shopman-app/shopman/channels.py (arquivo antigo, não confundir com channels/ app)
    - shopman-app/shopman/config.py (antigo)
    - shopman-app/shopman/presets.py (antigo)
    - shopman-app/nelson/
    - channels/web/models.py (StorefrontConfig)
12. Atualizar project/urls.py para novos import paths
13. Atualizar TODOS os imports nos testes

FASE 3 — Verificação:
14. make test — TODOS os testes devem passar
15. make lint — 0 warnings
16. Verificar: zero referências a mini-apps, nelson/, StorefrontConfig, config antigo
17. grep -r "shopman.inventory\|shopman.identification\|shopman.confirmation\|shopman.notifications\|shopman.payment\|shopman.pricing\|shopman.accounting\|shopman.fiscal\|shopman.returns\|shopman.webhook\|nelson\|StorefrontConfig" — deve retornar vazio
```

### WP-H1 — Order Save Seguro
```
Execute WP-H1 do HARDENING-PLAN.md: Order — Integridade Garantida pelo save().

Contexto: Timestamps, audit events e signals são INTEGRIDADE DE DADOS,
não lógica de negócio. Devem estar no save().

Leia HARDENING-PLAN.md seção WP-H1 para o código completo.

Passos:
1. Refatore Order.save():
   - Detectar mudança de status (self.status != self._original_status)
   - Validar transição (raise InvalidTransition se inválida)
   - Setar timestamp mecânico (confirmed_at, processing_at, etc.)
   - Após super().save(): emitir OrderEvent + signal order_changed
   - Actor via self._transition_actor (default "direct", limpo após save)

2. Simplifique Order.transition_status():
   - select_for_update() + set status + set _transition_actor + save()
   - O save() cuida do resto (timestamp, evento, signal)
   - Sync self após save

3. Testes novos:
   - test_direct_save_status_change_creates_event
   - test_direct_save_status_change_sets_timestamp
   - test_direct_save_status_change_sends_signal
   - test_direct_save_status_change_actor_is_direct
   - test_transition_status_actor_is_preserved
   - test_save_without_status_change_no_side_effects
   - test_invalid_transition_via_direct_save_raises

4. TODOS os testes existentes devem continuar passando sem mudanças
5. make test + make lint

Arquivo: shopman-core/ordering/shopman/ordering/models/order.py
```

### WP-H2 — Session Items
```
Execute WP-H2 do HARDENING-PLAN.md: Session Items — Comportamento Explícito.

Contexto: Session.save() tem efeito colateral oculto (persiste items do cache).
Documentar efeito colateral = documentar bug. Eliminar.

Leia HARDENING-PLAN.md seção WP-H2.

Passos:
1. Remova o setter de session.items (property vira read-only)
2. Crie session.update_items(items: list[dict]) que:
   - Normaliza items via _normalize_items()
   - Persiste imediatamente via _persist_items()
   - Atualiza _items_cache
3. Limpe Session.save() — remova a auto-persistência de items:
   - save() NÃO deve checar _items_cache nem chamar _persist_items
4. Atualize SessionManager.create(): use update_items() após super().create()
5. Atualize SessionManager.get_or_create(): idem
6. Atualize ModifyService: troque session.items = X por session.update_items(X)
7. Busque no codebase INTEIRO por "session.items =" e atualize cada ocorrência
8. Testes novos:
   - test_items_property_has_no_setter (AttributeError ou TypeError)
   - test_update_items_persists_to_database
   - test_save_does_not_persist_stale_items_cache
   - test_update_items_invalidates_and_refreshes_cache
9. make test + make lint

Arquivo: shopman-core/ordering/shopman/ordering/models/session.py
```

### WP-H3 — Directive on_commit
```
Execute WP-H3 do HARDENING-PLAN.md: Directives — Processamento Pós-Transação.

Contexto: Directives processadas via post_save DENTRO da transação.
Side effects externos (notificação, PIX) ocorrem mesmo se transação falha.
Solução: transaction.on_commit().

Leia HARDENING-PLAN.md seção WP-H3 para o código.

Passos:
1. Refatore dispatch.py:
   - post_save handler cria callback via transaction.on_commit()
   - No callback: re-fetch directive por pk (estado fresco pós-commit)
   - Se directive não existe ou não é "queued", skip (rollback ou já processada)
   - Manter reentrancy guard (_local.dispatching)
   - Manter opportunistic retry

2. Ajuste testes:
   - Use self.captureOnCommitCallbacks() (Django 4.2+) em TestCase
     para capturar e executar on_commit callbacks manualmente
   - Use TransactionTestCase APENAS para testes de rollback

3. Testes novos:
   - test_directive_processed_only_after_commit
   - test_directive_not_processed_on_rollback (TransactionTestCase)
   - test_refetch_ensures_fresh_state
   - test_reentrancy_guard_with_on_commit

4. Verifique que E2E flows (test_e2e_flow.py) continuam funcionando
5. make test + make lint

Arquivo: shopman-core/ordering/shopman/ordering/dispatch.py
```

### WP-H5 — Segurança
```
Execute WP-H5 do HARDENING-PLAN.md: Segurança Básica.

Passos:
1. settings.py — REST_FRAMEWORK:
   DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAuthenticated"]

2. ViewSets públicos (catálogo) — adicione permission_classes = [AllowAny]:
   - shopman-core/offering/shopman/offering/api/views.py (ProductViewSet, etc.)
   - Qualquer outro ViewSet que deve ser acessível sem login

3. project/urls.py — trocar try/except ImportError silencioso por logging:
   - Criar helper _include_optional(path, module) que loga se falha
   - Aplicar em TODAS as inclusões opcionais

4. settings.py — validação em produção:
   - assert SECRET_KEY != "dev-only" quando DEBUG=False
   - assert ALLOWED_HOSTS != ["*"] quando DEBUG=False

5. settings.py — security headers quando DEBUG=False:
   - SECURE_BROWSER_XSS_FILTER = True
   - SECURE_CONTENT_TYPE_NOSNIFF = True
   - X_FRAME_OPTIONS = "DENY"
   - SESSION_COOKIE_SECURE = True
   - CSRF_COOKIE_SECURE = True

6. Ajuste testes de API que falhem por falta de autenticação
   (force_authenticate ou APIClient com credentials)
7. make test + make lint

Arquivos: project/settings.py, project/urls.py, offering/api/views.py
```

### shopman.payments — Novo Core App
```
Execute a criação do shopman.payments conforme HARDENING-PLAN.md seção
"Novo Core App: shopman.payments".

1. Crie shopman-core/payments/ seguindo a estrutura dos outros core apps
   (pyproject.toml, shopman/payments/, models/, admin.py, tests/)
2. Crie PaymentIntent model conforme o plano (ref, order_ref string,
   method, status, amount_q, currency, gateway, gateway_id, gateway_data,
   timestamps)
3. Crie PaymentTransaction model (intent FK, type, amount_q, gateway_id)
4. Crie admin básico (list_display, filters, search)
5. Crie migration 0001_initial
6. Crie testes básicos (create intent, create transaction, status transitions)
7. Adicione "shopman.payments" ao INSTALLED_APPS
8. make test + make lint
```

---

## Critério de Aceite Global

1. `make test` — 100% (0 failures)
2. `make lint` — 0 warnings
3. Testes novos cobrem cenários descritos
4. Comportamento antigo eliminado (não basta adicionar o novo)
5. Zero resíduos do formato antigo
6. ChannelConfig validado — typos em config rejeitados com mensagem clara
7. Cascata funcional — Shop.defaults herdados por canais que não sobreescrevem
8. Pipeline legível — ao ler o preset, o fluxo inteiro é óbvio em 5 segundos

---

## Protocolo de Execução

Ao concluir um WP:
1. Rodar `make test` + `make lint`
2. Reportar resultado ao usuário
3. **Mostrar o texto completo do prompt do PRÓXIMO WP** (copiar do plano acima)
4. Se for o último WP da sequência, avisar: "Este foi o último WP do hardening."

Sequência: H0a → H0b → H0c → H0d → H1 → H2 → H5 → H3 → shopman.payments
