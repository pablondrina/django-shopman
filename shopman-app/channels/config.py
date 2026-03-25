"""
Channel configuration — 7 aspectos + cascata + validação.

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

    # ── 3. Estoque ──

    @dataclass
    class Stock:
        hold_ttl_minutes: int | None = None  # None = sem expiração
        safety_margin: int = 0
        planned_hold_ttl_hours: int = 48  # TTL for planned holds (fermata timeout)

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

    # ── 6. Regras ──

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

    # ── 7. Fluxo ──

    @dataclass
    class Flow:
        """Customização do fluxo de status."""

        transitions: dict[str, list[str]] | None = None
        terminal_statuses: list[str] | None = None
        auto_transitions: dict[str, str] | None = None
        auto_sync_fulfillment: bool = False

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
            confirmation=_safe_init(cls.Confirmation, data.get("confirmation", {})),
            payment=_safe_init(cls.Payment, data.get("payment", {})),
            stock=_safe_init(cls.Stock, data.get("stock", {})),
            pipeline=_safe_init(
                cls.Pipeline,
                {k: v for k, v in data.get("pipeline", {}).items() if k.startswith("on_")},
            ),
            notifications=_safe_init(cls.Notifications, data.get("notifications", {})),
            rules=_safe_init(cls.Rules, data.get("rules", {})),
            flow=_safe_init(
                cls.Flow,
                {k: v for k, v in data.get("flow", {}).items() if v is not None},
            ),
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
