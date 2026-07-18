"""FOMO badges (presentation/fomo.py) — derivação pura de urgência.

Cobre: limiar de últimas unidades, singular/plural, D-1, janela de frescor de
60 min, contagem regressiva de promoção, happy hour, ordenação por prioridade e
o teto de 2 badges por card. Sem banco: o módulo é puro.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from shopman.storefront.presentation.fomo import (
    FRESH_WINDOW_MINUTES,
    MAX_BADGES,
    FomoBadge,
    badges_for_product,
)

SKU = "croissant-trad"

NOW = timezone.make_aware(datetime(2026, 7, 18, 10, 0, 0), timezone.get_current_timezone())


def _types(badges) -> list[str]:
    return [badge.type for badge in badges]


def _by_type(badges, badge_type: str) -> FomoBadge:
    return next(badge for badge in badges if badge.type == badge_type)


# ── F1: últimas unidades ─────────────────────────────────────────────


class TestLowStock:
    def test_below_threshold_shows_count(self):
        badges = badges_for_product(
            SKU, availability={"available_qty": 3}, channel_config={"low_stock_threshold": 5}, now=NOW
        )
        assert _by_type(badges, "low_stock").label == "Últimas 3 unidades"

    def test_single_unit_is_singular(self):
        badges = badges_for_product(
            SKU, availability={"available_qty": 1}, channel_config={"low_stock_threshold": 5}, now=NOW
        )
        assert _by_type(badges, "low_stock").label == "Última unidade"

    def test_at_threshold_still_shows(self):
        badges = badges_for_product(
            SKU, availability={"available_qty": 5}, channel_config={"low_stock_threshold": 5}, now=NOW
        )
        assert "low_stock" in _types(badges)

    def test_above_threshold_is_silent(self):
        badges = badges_for_product(
            SKU, availability={"available_qty": 6}, channel_config={"low_stock_threshold": 5}, now=NOW
        )
        assert badges == ()

    def test_sold_out_shows_no_scarcity_badge(self):
        """Esgotado é responsabilidade do card ("Esgotado" + "Me avise"), não do FOMO."""
        badges = badges_for_product(SKU, availability={"available_qty": 0}, now=NOW)
        assert badges == ()

    def test_threshold_defaults_to_five(self):
        badges = badges_for_product(SKU, availability={"available_qty": 5}, now=NOW)
        assert "low_stock" in _types(badges)

    def test_decimal_string_quantity_is_coerced(self):
        badges = badges_for_product(SKU, availability={"available_qty": "2.0"}, now=NOW)
        assert _by_type(badges, "low_stock").label == "Últimas 2 unidades"


# ── F3: D-1 ──────────────────────────────────────────────────────────


class TestD1:
    def test_d1_stock_shows_last_day_badge(self):
        badges = badges_for_product(SKU, availability={"d1_qty": 4}, now=NOW)
        assert _by_type(badges, "d1").label == "Último dia: amanhã não tem"

    def test_no_d1_stock_is_silent(self):
        badges = badges_for_product(SKU, availability={"d1_qty": 0}, now=NOW)
        assert "d1" not in _types(badges)

    def test_label_never_uses_em_dash(self):
        """Travessão é proibido na copy do cliente."""
        badges = badges_for_product(SKU, availability={"d1_qty": 1}, now=NOW)
        assert "—" not in _by_type(badges, "d1").label


# ── F5: saiu do forno ────────────────────────────────────────────────


class TestFresh:
    def test_just_finished_reads_agora(self):
        badges = badges_for_product(SKU, production={"finished_at": NOW}, now=NOW)
        assert _by_type(badges, "fresh").label == "Saiu do forno agora"

    def test_minutes_ago_is_counted(self):
        finished = NOW - timedelta(minutes=12)
        badges = badges_for_product(SKU, production={"finished_at": finished}, now=NOW)
        assert _by_type(badges, "fresh").label == "Saiu do forno há 12 min"

    def test_iso_string_is_accepted(self):
        finished = (NOW - timedelta(minutes=8)).isoformat()
        badges = badges_for_product(SKU, production={"finished_at": finished}, now=NOW)
        assert _by_type(badges, "fresh").label == "Saiu do forno há 8 min"

    def test_expires_sixty_minutes_after_the_bake(self):
        finished = NOW - timedelta(minutes=10)
        badges = badges_for_product(SKU, production={"finished_at": finished}, now=NOW)
        expected = (finished + timedelta(minutes=FRESH_WINDOW_MINUTES)).isoformat()
        assert _by_type(badges, "fresh").expires_at == expected

    def test_beyond_the_window_is_silent(self):
        finished = NOW - timedelta(minutes=FRESH_WINDOW_MINUTES + 1)
        badges = badges_for_product(SKU, production={"finished_at": finished}, now=NOW)
        assert "fresh" not in _types(badges)

    def test_at_the_window_edge_still_shows(self):
        finished = NOW - timedelta(minutes=FRESH_WINDOW_MINUTES)
        badges = badges_for_product(SKU, production={"finished_at": finished}, now=NOW)
        assert "fresh" in _types(badges)

    def test_future_bake_is_not_fresh_yet(self):
        finished = NOW + timedelta(minutes=5)
        badges = badges_for_product(SKU, production={"finished_at": finished}, now=NOW)
        assert badges == ()

    @pytest.mark.parametrize("production", [None, {}, {"finished_at": None}, {"finished_at": "lixo"}])
    def test_missing_or_broken_production_is_silent(self, production):
        assert badges_for_product(SKU, production=production, now=NOW) == ()


# ── F13: promoção expirando ──────────────────────────────────────────


class TestPromoCountdown:
    def test_promo_closing_soon_counts_down(self):
        promos = [{"name": "Terça do pão", "valid_until": NOW + timedelta(hours=2)}]
        badges = badges_for_product(SKU, promotions=promos, now=NOW)
        assert _by_type(badges, "promo_countdown").label == "Promoção acaba em 2h"

    def test_under_an_hour_reads_menos_de_1h(self):
        promos = [{"valid_until": NOW + timedelta(minutes=20)}]
        badges = badges_for_product(SKU, promotions=promos, now=NOW)
        assert _by_type(badges, "promo_countdown").label == "Promoção acaba em menos de 1h"

    def test_far_away_promo_is_silent(self):
        promos = [{"valid_until": NOW + timedelta(hours=30)}]
        assert badges_for_product(SKU, promotions=promos, now=NOW) == ()

    def test_expired_promo_is_silent(self):
        promos = [{"valid_until": NOW - timedelta(hours=1)}]
        assert badges_for_product(SKU, promotions=promos, now=NOW) == ()


# ── F14: happy hour ──────────────────────────────────────────────────


class TestHappyHour:
    def test_active_happy_hour_shows_end_time(self):
        badges = badges_for_product(
            SKU, availability={"has_happy_hour": True, "happy_hour_end": "18:00"}, now=NOW
        )
        assert _by_type(badges, "happy_hour").label == "Happy Hour até 18:00"

    def test_without_end_time_falls_back(self):
        badges = badges_for_product(SKU, availability={"has_happy_hour": True}, now=NOW)
        assert _by_type(badges, "happy_hour").label == "Happy Hour agora"

    def test_inactive_is_silent(self):
        badges = badges_for_product(SKU, availability={"has_happy_hour": False}, now=NOW)
        assert badges == ()


# ── Prioridade e teto ────────────────────────────────────────────────


class TestPriorityAndCap:
    def _everything(self):
        return badges_for_product(
            SKU,
            availability={
                "available_qty": 2,
                "d1_qty": 3,
                "has_happy_hour": True,
                "happy_hour_end": "18:00",
            },
            production={"finished_at": NOW - timedelta(minutes=5)},
            promotions=[{"valid_until": NOW + timedelta(hours=1)}],
            now=NOW,
        )

    def test_never_shows_more_than_two(self):
        assert len(self._everything()) == MAX_BADGES

    def test_most_urgent_win(self):
        assert _types(self._everything()) == ["fresh", "low_stock"]

    def test_ordered_by_priority(self):
        badges = badges_for_product(
            SKU,
            availability={"d1_qty": 1, "has_happy_hour": True},
            now=NOW,
        )
        assert [badge.priority for badge in badges] == sorted(badge.priority for badge in badges)

    def test_no_signal_no_badges(self):
        assert badges_for_product(SKU, now=NOW) == ()

    def test_meta_carries_the_sku(self):
        badges = badges_for_product(SKU, availability={"available_qty": 1}, now=NOW)
        assert badges[0].meta["sku"] == SKU
