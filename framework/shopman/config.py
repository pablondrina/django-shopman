"""
Channel configuration — 8 aspectos + cascata + validação.

Configuração completa de um canal de venda. Cada aspecto responde a UMA pergunta.
Cascata: canal → loja → defaults.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ChannelConfig:
    """
    Configuração completa de um canal de venda.

    confirmation  — como o pedido é aceito?
    payment       — como e quando o cliente paga?
    fulfillment   — quando criar fulfillment?
    stock         — comportamento de reserva de estoque
    notifications — por onde avisamos?
    pricing       — como o preço é definido? (internal/external)
    editing       — itens podem ser editados? (open/locked)
    rules         — quais validators/modifiers ativar?
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
        method: str | list[str] = "counter"
        # str or list[str]:
        # "counter"  — no caixa/entrega
        # "pix"      — PIX com QR code
        # "card"     — cartão via Stripe
        # "external" — já pago (marketplace)
        # ["pix", "card"] — múltiplos métodos (cliente escolhe)
        timing: str = "post_commit"
        # "post_commit" — initiate payment after order confirmed (default for remote)
        # "at_commit"   — initiate payment at commit time
        # "external"    — no digital payment (local counter / marketplace)
        timeout_minutes: int = 15  # só para method=pix

        @property
        def available_methods(self) -> list[str]:
            """Always returns a list of payment methods."""
            if isinstance(self.method, list):
                return self.method
            return [self.method]

    # ── 3. Fulfillment ──

    @dataclass
    class Fulfillment:
        timing: str = "post_commit"
        # "at_commit"   — create fulfillment at commit time
        # "post_commit" — create fulfillment when order is ready (default)
        # "external"    — handled externally (marketplace)
        auto_sync: bool = True

    # ── 4. Estoque ──

    @dataclass
    class Stock:
        hold_ttl_minutes: int | None = None  # None = sem expiração
        safety_margin: int = 0
        planned_hold_ttl_hours: int = 48  # TTL for planned holds (fermata timeout)
        allowed_positions: list[str] | None = None  # None = all saleable positions
        check_on_commit: bool = False  # validate per-item availability at commit

    # ── 5. Notificações ──
    @dataclass
    class Notifications:
        backend: str = "manychat"
        # "manychat" | "email" | "console" | "sms" | "webhook" | "none"
        # Prioridade phone-first (Brasil): manychat (WhatsApp) > sms > email > console
        fallback_chain: list[str] = field(default_factory=lambda: ["sms", "email"])
        routing: dict[str, str] | None = None

    # ── 6. Pricing ──

    @dataclass
    class Pricing:
        policy: str = "internal"
        # "internal" — preço resolvido pelo backend (padrão para canais próprios)
        # "external" — preço definido externamente (marketplace)

    # ── 7. Editing ──

    @dataclass
    class Editing:
        policy: str = "open"
        # "open"   — itens podem ser editados após adição (padrão)
        # "locked" — itens não podem ser editados (marketplace)

    # ── 8. Regras ──

    @dataclass
    class Rules:
        """Validators, modifiers e checks ativos neste canal.

        Herança via cascata (deep_merge no nível de dict):
        - Chave ausente = herda do nível anterior
        - Lista explícita = sobreescreve
        - Lista vazia [] = desativa
        """

        validators: list[str] = field(default_factory=list)
        modifiers: list[str] = field(default_factory=list)
        checks: list[str] = field(default_factory=list)

    # ── Campos ──

    confirmation: Confirmation = field(default_factory=Confirmation)
    payment: Payment = field(default_factory=Payment)
    fulfillment: Fulfillment = field(default_factory=Fulfillment)
    stock: Stock = field(default_factory=Stock)
    notifications: Notifications = field(default_factory=Notifications)
    pricing: Pricing = field(default_factory=Pricing)
    editing: Editing = field(default_factory=Editing)
    rules: Rules = field(default_factory=Rules)

    # ── UX ──

    handle_label: str = "Identificador"
    # Label exibido na UI para o campo handle_ref da sessão/pedido.
    # Ex: "Comanda" (restaurante), "Mesa" (self-service), "CPF" (e-commerce).
    handle_placeholder: str = ""
    # Placeholder sugerido para o campo handle_ref.
    # Ex: "Ex: 42", "Ex: mesa 3".

    # ── Serialização ──

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ChannelConfig:
        return cls(
            confirmation=_safe_init(cls.Confirmation, data.get("confirmation", {})),
            payment=_safe_init(cls.Payment, data.get("payment", {})),
            fulfillment=_safe_init(cls.Fulfillment, data.get("fulfillment", {})),
            stock=_safe_init(cls.Stock, data.get("stock", {})),
            notifications=_safe_init(cls.Notifications, data.get("notifications", {})),
            pricing=_safe_init(cls.Pricing, data.get("pricing", {})),
            editing=_safe_init(cls.Editing, data.get("editing", {})),
            rules=_safe_init(cls.Rules, data.get("rules", {})),
            handle_label=data.get("handle_label", cls.handle_label),
            handle_placeholder=data.get("handle_placeholder", cls.handle_placeholder),
        )

    @classmethod
    def defaults(cls) -> dict:
        return cls().to_dict()

    # ── Cascata ──

    @classmethod
    def for_channel(cls, channel_or_ref) -> "ChannelConfig":
        """
        Config resolvido para este canal: canal ← loja ← defaults.

        Aceita um objeto Channel (shopman.Channel) ou uma string channel_ref.

        Cascata completa:
          1. Defaults hardcoded (ChannelConfig())
          2. Shop.defaults (nível loja, Admin-configurável)
          3. Channel.config (nível canal, Admin-configurável)
        """
        from shopman.models import Channel, Shop

        base = cls.defaults()

        # Nível loja
        shop = Shop.load()
        if shop and shop.defaults:
            base = deep_merge(base, shop.defaults)

        # Nível canal
        if isinstance(channel_or_ref, str):
            channel_ref = channel_or_ref
            try:
                channel = Channel.objects.get(ref=channel_ref)
            except Channel.DoesNotExist:
                channel = None
        else:
            channel = channel_or_ref

        if channel and channel.config:
            base = deep_merge(base, channel.config)

        return cls.from_dict(base)

    # ── Validação ──

    def validate(self):
        if self.confirmation.mode not in ("immediate", "optimistic", "manual"):
            raise ValueError(f"confirmation.mode inválido: {self.confirmation.mode}")
        if self.confirmation.mode == "optimistic" and self.confirmation.timeout_minutes <= 0:
            raise ValueError("timeout_minutes deve ser > 0 para mode=optimistic")
        valid_methods = {"counter", "pix", "card", "external"}
        for m in self.payment.available_methods:
            if m not in valid_methods:
                raise ValueError(f"payment.method inválido: {m}")
        if "pix" in self.payment.available_methods and self.payment.timeout_minutes <= 0:
            raise ValueError("timeout_minutes deve ser > 0 para method=pix")
        valid_timings = {"pre_commit", "at_commit", "post_commit", "external"}
        if self.payment.timing not in valid_timings:
            raise ValueError(f"payment.timing inválido: {self.payment.timing}")
        if self.fulfillment.timing not in valid_timings:
            raise ValueError(f"fulfillment.timing inválido: {self.fulfillment.timing}")
        if self.pricing.policy not in ("internal", "external"):
            raise ValueError(f"pricing.policy inválido: {self.pricing.policy}")
        if self.editing.policy not in ("open", "locked"):
            raise ValueError(f"editing.policy inválido: {self.editing.policy}")


def _safe_init(cls, data: dict):
    """Instantiate a dataclass filtering out unknown fields."""
    import dataclasses

    valid_fields = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return cls(**filtered)


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
