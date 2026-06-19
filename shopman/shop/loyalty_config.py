"""Loyalty defaults — ``Shop.defaults["loyalty"]`` dataclass + resolution.

Shop-level loyalty policy, editável no Admin (ShopForm) e lido pela camada
orquestradora:

- ``points_per_real`` — taxa de acúmulo (pontos por R$ 1,00), lida pelo
  ``LoyaltyEarnHandler``.
- ``tiers`` — limiares dos níveis (bronze/prata/ouro/platina), injetados no
  Core (guestman) que faz o auto-upgrade.
- ``stamps_target`` — meta padrão de carimbos de novas contas.

O Core (guestman) NÃO depende do shop: o orquestrador registra resolvers em
``shopman.shop.apps`` que alimentam ``guestman.contrib.loyalty.conf``. Aqui mora
o source-of-truth tipado (dataclass), seguindo o padrão dataclass-driven do
``Shop.defaults`` (espelha ``pickup_slots``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Os tiers mapeiam para guestman.LoyaltyTier (bronze/silver/gold/platinum).
# Ordem canônica = crescente por limiar (bronze é o piso, sempre em 0).
TIER_NAMES: tuple[str, ...] = ("bronze", "silver", "gold", "platinum")
TIER_LABELS: dict[str, str] = {
    "bronze": "Bronze",
    "silver": "Prata",
    "gold": "Ouro",
    "platinum": "Platina",
}

DEFAULT_POINTS_PER_REAL = 1
DEFAULT_STAMPS_TARGET = 10
DEFAULT_TIERS: list[dict] = [
    {"name": "bronze", "threshold": 0},
    {"name": "silver", "threshold": 500},
    {"name": "gold", "threshold": 2000},
    {"name": "platinum", "threshold": 5000},
]


@dataclass
class LoyaltyConfig:
    """Política de fidelidade resolvida (defaults ← Shop.defaults["loyalty"])."""

    points_per_real: int = DEFAULT_POINTS_PER_REAL
    stamps_target: int = DEFAULT_STAMPS_TARGET
    tiers: list[dict] = field(default_factory=lambda: [dict(t) for t in DEFAULT_TIERS])

    @classmethod
    def from_defaults(cls, defaults: dict | None) -> LoyaltyConfig:
        """Constrói a partir de ``Shop.defaults`` (chaves ausentes → defaults)."""
        block: dict = {}
        if isinstance(defaults, dict) and isinstance(defaults.get("loyalty"), dict):
            block = defaults["loyalty"]
        return cls(
            points_per_real=_coerce_non_negative_int(
                block.get("points_per_real"), DEFAULT_POINTS_PER_REAL
            ),
            stamps_target=_coerce_non_negative_int(
                block.get("stamps_target"), DEFAULT_STAMPS_TARGET
            ),
            tiers=_normalize_tiers(block.get("tiers")),
        )

    def tier_thresholds(self) -> list[tuple[int, str]]:
        """``[(threshold, name)]`` decrescente, como ``_update_tier`` espera."""
        pairs = [(int(t["threshold"]), str(t["name"])) for t in self.tiers]
        pairs.sort(key=lambda pair: pair[0], reverse=True)
        return pairs

    def to_dict(self) -> dict:
        return {
            "points_per_real": self.points_per_real,
            "stamps_target": self.stamps_target,
            "tiers": [dict(t) for t in self.tiers],
        }


def _coerce_non_negative_int(value, fallback: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return fallback
    return coerced if coerced >= 0 else fallback


def _normalize_tiers(raw) -> list[dict]:
    """Sanea os tiers: nomes válidos, limiares >= 0, bronze sempre em 0."""
    by_name: dict[str, int] = {}
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict) or entry.get("name") not in TIER_NAMES:
                continue
            try:
                threshold = max(0, int(entry.get("threshold", 0)))
            except (TypeError, ValueError):
                continue
            by_name[entry["name"]] = threshold
    if not by_name:
        return [dict(t) for t in DEFAULT_TIERS]
    by_name["bronze"] = 0  # bronze é o piso, sempre presente em 0
    return [{"name": name, "threshold": by_name[name]} for name in TIER_NAMES if name in by_name]


def resolve_loyalty_config() -> LoyaltyConfig:
    """Política de fidelidade efetiva, a partir do ``Shop`` singleton."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    return LoyaltyConfig.from_defaults(defaults)
