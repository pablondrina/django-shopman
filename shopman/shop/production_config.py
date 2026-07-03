"""
Production configuration — contrato único + cascata + validação.

Equivalente de ``ChannelConfig`` para o domínio de produção: todo knob que
governa sugestão, alertas e vínculo pedido↔produção vive aqui, lido de
``Shop.defaults["production"]`` com defaults sensatos. Nenhum consumidor lê
constantes hardcoded ou chaves cruas de JSONField.

Cascata: ``Shop.defaults["production"]`` → defaults deste dataclass.
(Produção é da loja, não do canal — não há nível de canal.)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation


@dataclass
class ProductionConfig:
    """
    Configuração de produção da loja.

    suggestion    — como a sugestão de produção é calculada?
    alerts        — quando o operador é avisado na tela?
    notifications — quais alertas também viram notificação (email/console)?
    order_match   — como pedidos confirmados se vinculam a WorkOrders?
    """

    # ── 1. Sugestão ──

    @dataclass
    class Suggestion:
        seasons: dict = field(default_factory=dict)
        # {"hot": [10, 11, 12, 1, 2, 3], "mild": [4, 5, 9], "cold": [6, 7, 8]}
        # Mês corrente resolve a estação; a lista de meses filtra o histórico
        # de demanda do craft.suggest(). Vazio = sem filtro sazonal.
        high_demand_multiplier: str | None = None
        # Decimal-string (ex: "1.2") aplicada em sexta/sábado. None = desligado.
        safety_stock_percent: str | None = None
        # Decimal-string (ex: "0.20") — margem sobre (demanda + committed).
        # None = default do Core (CRAFTSMAN["SAFETY_STOCK_PERCENT"]).
        horizon_days: int = 1
        # Data-alvo padrão do planejamento (1 = amanhã).

        @property
        def high_demand_multiplier_decimal(self) -> Decimal | None:
            return _decimal_or_none(self.high_demand_multiplier)

        @property
        def safety_stock_percent_decimal(self) -> Decimal | None:
            return _decimal_or_none(self.safety_stock_percent)

        def season_months_for(self, month: int) -> list[int] | None:
            """Meses da estação que contém ``month`` (None = sem filtro)."""
            for months in (self.seasons or {}).values():
                if isinstance(months, list) and month in months:
                    return [int(m) for m in months]
            return None

    # ── 2. Alertas ──

    @dataclass
    class Alerts:
        low_yield_threshold: str = "0.80"
        # Yield (finished/started) abaixo disto → OperatorAlert production_low_yield.
        default_max_started_minutes: int = 240
        # Janela padrão de produção em andamento; Recipe.meta["max_started_minutes"]
        # sobreescreve por receita.
        late_check_cadence_minutes: int = 15
        # Cadência do heartbeat production.late_check (0 = desligado).

        @property
        def low_yield_threshold_decimal(self) -> Decimal:
            return Decimal(self.low_yield_threshold)

    # ── 3. Notificações ──

    @dataclass
    class Notifications:
        enabled: bool = False
        # Desligado por padrão: alerta de produção sempre aparece na tela
        # (OperatorAlert); notificação ativa (email/console via directive)
        # é opt-in para não virar ruído.
        severities: list[str] = field(default_factory=lambda: ["error"])
        # Severidades que notificam quando enabled. Default: só crítico
        # (estoque insuficiente); ampliar para ["error", "warning"] cobre
        # atraso/yield/esquecimento.

    # ── Campos ──

    suggestion: Suggestion = field(default_factory=Suggestion)
    alerts: Alerts = field(default_factory=Alerts)
    notifications: Notifications = field(default_factory=Notifications)
    order_match: str = "first_planned"
    # "first_planned" | "earliest_target" | "manual" — estratégia de vínculo
    # pedido confirmado → WorkOrder (production_order_sync).

    # ── Serialização ──

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProductionConfig:
        return cls(
            suggestion=_safe_init(cls.Suggestion, data.get("suggestion", {})),
            alerts=_safe_init(cls.Alerts, data.get("alerts", {})),
            notifications=_safe_init(cls.Notifications, data.get("notifications", {})),
            order_match=data.get("order_match", cls.order_match),
        )

    @classmethod
    def defaults(cls) -> dict:
        return cls().to_dict()

    # ── Cascata ──

    @classmethod
    def load(cls) -> ProductionConfig:
        """Config resolvida da loja: ``Shop.defaults["production"]`` ← defaults."""
        from shopman.shop.config import deep_merge
        from shopman.shop.models import Shop

        base = cls.defaults()
        shop = Shop.load()
        overrides = (shop.defaults or {}).get("production") if shop else None
        if isinstance(overrides, dict):
            base = deep_merge(base, overrides)

        config = cls.from_dict(base)
        config.validate()
        return config

    # ── Validação ──

    def validate(self):
        if not isinstance(self.suggestion.seasons, dict):
            raise ValueError("production.suggestion.seasons deve ser um dict")
        for season, months in self.suggestion.seasons.items():
            if not isinstance(months, list) or not all(
                isinstance(m, int) and 1 <= m <= 12 for m in months
            ):
                raise ValueError(
                    f"production.suggestion.seasons[{season!r}] deve ser lista de meses 1-12"
                )
        _require_decimal_or_none(
            self.suggestion.high_demand_multiplier,
            "production.suggestion.high_demand_multiplier",
            minimum=Decimal("0"),
        )
        _require_decimal_or_none(
            self.suggestion.safety_stock_percent,
            "production.suggestion.safety_stock_percent",
            minimum=Decimal("0"),
        )
        if self.suggestion.horizon_days < 0:
            raise ValueError("production.suggestion.horizon_days deve ser >= 0")

        threshold = _require_decimal_or_none(
            self.alerts.low_yield_threshold, "production.alerts.low_yield_threshold"
        )
        if threshold is None or not (Decimal("0") <= threshold <= Decimal("1")):
            raise ValueError("production.alerts.low_yield_threshold deve estar entre 0 e 1")
        if self.alerts.default_max_started_minutes <= 0:
            raise ValueError("production.alerts.default_max_started_minutes deve ser > 0")
        if self.alerts.late_check_cadence_minutes < 0:
            raise ValueError("production.alerts.late_check_cadence_minutes deve ser >= 0")

        if not isinstance(self.notifications.enabled, bool):
            raise ValueError("production.notifications.enabled deve ser booleano")
        if not isinstance(self.notifications.severities, list) or not all(
            severity in ("info", "warning", "error", "critical")
            for severity in self.notifications.severities
        ):
            raise ValueError(
                "production.notifications.severities deve ser lista de "
                "info|warning|error|critical"
            )

        if self.order_match not in ("first_planned", "earliest_target", "manual"):
            raise ValueError(f"production.order_match inválido: {self.order_match}")


def _safe_init(cls, data: dict):
    """Instancia um dataclass filtrando campos desconhecidos."""
    import dataclasses

    valid_fields = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return cls(**filtered)


def _decimal_or_none(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _require_decimal_or_none(value, label: str, *, minimum: Decimal | None = None) -> Decimal | None:
    try:
        parsed = _decimal_or_none(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label} deve ser um decimal válido") from exc
    if parsed is not None and minimum is not None and parsed < minimum:
        raise ValueError(f"{label} deve ser >= {minimum}")
    return parsed
