"""WP-1 — Fidelidade admin-configurável (Shop.defaults["loyalty"]).

Cobre o dataclass, a resolução a partir do Shop, a injeção no Core (guestman)
sem acoplamento, e o uso da taxa de acúmulo pelo earn handler.
"""

from __future__ import annotations

import pytest

from shopman.shop.loyalty_config import (
    DEFAULT_POINTS_PER_REAL,
    DEFAULT_STAMPS_TARGET,
    DEFAULT_TIERS,
    LoyaltyConfig,
    resolve_loyalty_config,
)

# ── Dataclass ────────────────────────────────────────────────────────


class TestLoyaltyConfigDataclass:
    def test_defaults_match_legacy_behavior(self):
        config = LoyaltyConfig.from_defaults(None)
        assert config.points_per_real == DEFAULT_POINTS_PER_REAL == 1
        assert config.stamps_target == DEFAULT_STAMPS_TARGET == 10
        assert config.tiers == DEFAULT_TIERS

    def test_empty_loyalty_block_uses_defaults(self):
        config = LoyaltyConfig.from_defaults({"loyalty": {}})
        assert config.points_per_real == 1
        assert config.tiers == DEFAULT_TIERS

    def test_overrides_applied(self):
        config = LoyaltyConfig.from_defaults({
            "loyalty": {
                "points_per_real": 2,
                "stamps_target": 8,
                "tiers": [
                    {"name": "bronze", "threshold": 0},
                    {"name": "silver", "threshold": 300},
                    {"name": "gold", "threshold": 1500},
                ],
            }
        })
        assert config.points_per_real == 2
        assert config.stamps_target == 8
        assert config.tier_thresholds() == [(1500, "gold"), (300, "silver"), (0, "bronze")]

    def test_points_per_real_zero_disables_earning(self):
        config = LoyaltyConfig.from_defaults({"loyalty": {"points_per_real": 0}})
        assert config.points_per_real == 0

    def test_garbage_values_fall_back_to_defaults(self):
        config = LoyaltyConfig.from_defaults({
            "loyalty": {"points_per_real": "abc", "stamps_target": -5}
        })
        assert config.points_per_real == 1
        assert config.stamps_target == 10

    def test_normalize_filters_invalid_tier_names_and_forces_bronze_floor(self):
        config = LoyaltyConfig.from_defaults({
            "loyalty": {
                "tiers": [
                    {"name": "bronze", "threshold": 999},  # bronze forçado a 0
                    {"name": "diamond", "threshold": 100},  # nome inválido → descartado
                    {"name": "gold", "threshold": 1000},
                ]
            }
        })
        names = {t["name"]: t["threshold"] for t in config.tiers}
        assert names == {"bronze": 0, "gold": 1000}

    def test_tier_thresholds_descending(self):
        config = LoyaltyConfig.from_defaults(None)
        thresholds = config.tier_thresholds()
        assert thresholds == sorted(thresholds, key=lambda p: p[0], reverse=True)
        assert thresholds[-1] == (0, "bronze")


# ── Resolução a partir do Shop ───────────────────────────────────────


@pytest.mark.django_db
class TestResolveLoyaltyConfig:
    def test_no_shop_returns_defaults(self):
        config = resolve_loyalty_config()
        assert config.points_per_real == 1
        assert config.stamps_target == 10

    def test_reads_shop_defaults(self):
        from shopman.shop.models import Shop

        Shop.objects.create(
            name="Loja",
            defaults={"loyalty": {"points_per_real": 3, "stamps_target": 6}},
        )
        config = resolve_loyalty_config()
        assert config.points_per_real == 3
        assert config.stamps_target == 6


# ── Injeção no Core (guestman) sem acoplamento ───────────────────────


class TestGuestmanResolverInjection:
    """Save/restore the app-registered resolver — never leak ``None`` to the
    rest of the test session (apps.ready wires the live resolver)."""

    def test_set_and_clear_tier_resolver(self):
        from shopman.guestman.contrib.loyalty import conf

        original = conf._tier_thresholds_resolver
        custom = [(100, "gold"), (10, "silver"), (0, "bronze")]
        try:
            conf.set_tier_thresholds_resolver(lambda: custom)
            assert conf.get_tier_thresholds() == custom
            conf.set_tier_thresholds_resolver(None)
            # Cleared → falls back to settings/default
            assert conf.get_tier_thresholds() == conf._DEFAULT_TIER_THRESHOLDS
        finally:
            conf.set_tier_thresholds_resolver(original)

    def test_empty_resolver_result_falls_back(self):
        from shopman.guestman.contrib.loyalty import conf

        original = conf._tier_thresholds_resolver
        try:
            conf.set_tier_thresholds_resolver(lambda: [])
            assert conf.get_tier_thresholds() == conf._DEFAULT_TIER_THRESHOLDS
        finally:
            conf.set_tier_thresholds_resolver(original)

    def test_stamps_target_resolver(self):
        from shopman.guestman.contrib.loyalty import conf

        original = conf._default_stamps_target_resolver
        try:
            conf.set_default_stamps_target_resolver(lambda: 7)
            assert conf.get_default_stamps_target() == 7
            conf.set_default_stamps_target_resolver(None)
            assert conf.get_default_stamps_target() == conf._DEFAULT_STAMPS_TARGET
        finally:
            conf.set_default_stamps_target_resolver(original)


# ── Wiring vivo: Shop → guestman ─────────────────────────────────────


@pytest.mark.django_db
class TestLiveWiring:
    def test_enroll_uses_shop_stamps_target(self):
        from shopman.guestman.contrib.loyalty.service import LoyaltyService
        from shopman.guestman.models import Customer

        from shopman.shop.models import Shop

        Shop.objects.create(name="Loja", defaults={"loyalty": {"stamps_target": 5}})
        Customer.objects.create(ref="CLI-STAMP", first_name="Ana", phone="+5543999990000")

        account = LoyaltyService.enroll("CLI-STAMP")
        assert account.stamps_target == 5

    def test_tier_upgrade_respects_shop_thresholds(self):
        from shopman.guestman.contrib.loyalty.models import LoyaltyTier
        from shopman.guestman.contrib.loyalty.service import LoyaltyService
        from shopman.guestman.models import Customer

        from shopman.shop.models import Shop

        # Silver bem mais baixo que o default (500) → 100 pontos já sobe.
        Shop.objects.create(
            name="Loja",
            defaults={"loyalty": {"tiers": [
                {"name": "bronze", "threshold": 0},
                {"name": "silver", "threshold": 50},
            ]}},
        )
        Customer.objects.create(ref="CLI-TIER", first_name="Beto", phone="+5543999990001")
        LoyaltyService.enroll("CLI-TIER")
        LoyaltyService.earn_points("CLI-TIER", 100, "Compra")

        account = LoyaltyService.get_account("CLI-TIER")
        assert account.tier == LoyaltyTier.SILVER


# ── Earn handler usa points_per_real ─────────────────────────────────


@pytest.mark.django_db
class TestEarnHandlerRate:
    def _run(self, total_q, shop_defaults=None):
        from shopman.guestman.contrib.loyalty.service import LoyaltyService
        from shopman.guestman.models import Customer
        from shopman.orderman.models import Directive, Order

        from shopman.shop.handlers.loyalty import LoyaltyEarnHandler
        from shopman.shop.models import Shop

        if shop_defaults is not None:
            Shop.objects.create(name="Loja", defaults=shop_defaults)
        Customer.objects.create(ref="CLI-EARN", first_name="Cláudia", phone="+5543999990002")
        order = Order.objects.create(
            ref="ORD-EARN-1",
            channel_ref="web",
            status="completed",
            total_q=total_q,
            data={"customer_ref": "CLI-EARN"},
        )
        directive = Directive(topic="loyalty.earn", payload={"order_ref": order.ref})
        LoyaltyEarnHandler().handle(message=directive, ctx={})
        return LoyaltyService.get_balance("CLI-EARN")

    def test_default_rate_one_point_per_real(self):
        assert self._run(5000) == 50

    def test_configured_rate_doubles_points(self):
        assert self._run(5000, {"loyalty": {"points_per_real": 2}}) == 100

    def test_zero_rate_awards_nothing(self):
        assert self._run(5000, {"loyalty": {"points_per_real": 0}}) == 0
