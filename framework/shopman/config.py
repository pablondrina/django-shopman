"""
Channel configuration — 6 aspectos + cascata + validação.

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
    payment       — como o cliente paga?
    stock         — comportamento de reserva de estoque
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
        method: str | list[str] = "counter"
        # str or list[str]:
        # "counter"  — no caixa/entrega
        # "pix"      — PIX com QR code
        # "card"     — cartão via Stripe
        # "external" — já pago (marketplace)
        # ["pix", "card"] — múltiplos métodos (cliente escolhe)
        timeout_minutes: int = 15  # só para method=pix

        @property
        def available_methods(self) -> list[str]:
            """Always returns a list of payment methods."""
            if isinstance(self.method, list):
                return self.method
            return [self.method]

    # ── 3. Estoque ──

    @dataclass
    class Stock:
        hold_ttl_minutes: int | None = None  # None = sem expiração
        safety_margin: int = 0
        planned_hold_ttl_hours: int = 48  # TTL for planned holds (fermata timeout)
        allowed_positions: list[str] | None = None  # None = all saleable positions

    # ── 4. Notificações ──
    @dataclass
    class Notifications:
        backend: str = "manychat"
        # "manychat" | "email" | "console" | "sms" | "webhook" | "none"
        # Prioridade phone-first (Brasil): manychat (WhatsApp) > sms > email > console
        fallback_chain: list[str] = field(default_factory=lambda: ["sms", "email"])
        routing: dict[str, str] | None = None

    # ── 5. Regras ──

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

    # ── 6. Fluxo ──

    @dataclass
    class Flow:
        """Customização do fluxo de status."""

        transitions: dict[str, list[str]] | None = None
        terminal_statuses: list[str] | None = None
        auto_transitions: dict[str, str] | None = None
        # Chaves canônicas de auto_transitions:
        #   "on_paid" — dispara quando webhook de pagamento confirma (PIX/Stripe)
        #   Mapeiam para o status-alvo: {"on_paid": "confirmed"}
        auto_sync_fulfillment: bool = False

    # ── Campos ──

    confirmation: Confirmation = field(default_factory=Confirmation)
    payment: Payment = field(default_factory=Payment)
    stock: Stock = field(default_factory=Stock)
    notifications: Notifications = field(default_factory=Notifications)
    rules: Rules = field(default_factory=Rules)
    flow: Flow = field(default_factory=Flow)

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
            stock=_safe_init(cls.Stock, data.get("stock", {})),
            notifications=_safe_init(cls.Notifications, data.get("notifications", {})),
            rules=_safe_init(cls.Rules, data.get("rules", {})),
            flow=_safe_init(
                cls.Flow,
                {k: v for k, v in data.get("flow", {}).items() if v is not None},
            ),
            handle_label=data.get("handle_label", cls.handle_label),
            handle_placeholder=data.get("handle_placeholder", cls.handle_placeholder),
        )

    @classmethod
    def defaults(cls) -> dict:
        return cls().to_dict()

    # ── Cascata ──

    @classmethod
    def for_channel(cls, channel) -> "ChannelConfig":
        """
        Config resolvido para este canal: canal ← loja ← defaults.

        Cascata completa:
          1. Defaults hardcoded (ChannelConfig())
          2. Shop.defaults (nível loja, Admin-configurável)
          3. ChannelConfigRecord.data para channel.ref (nível canal, Admin-configurável)
        """
        from shopman.models import Shop, ChannelConfigRecord

        base = cls.defaults()

        # Nível loja
        shop = Shop.load()
        if shop and shop.defaults:
            base = deep_merge(base, shop.defaults)

        # Nível canal
        channel_ref = getattr(channel, "ref", None)
        if channel_ref:
            record = ChannelConfigRecord.objects.filter(channel_ref=channel_ref).first()
            if record and record.data:
                base = deep_merge(base, record.data)

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
