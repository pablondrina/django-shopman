"""Unit tests for shopman.shop.projections.cart.

Uses the `cart_session` fixture (from conftest.py) which seeds a cart with
the default product, so the projection builder has a real Orderman session
+ ListingItem + stock to work against.
"""
from __future__ import annotations

import json

import pytest
from django.test import RequestFactory
from shopman.orderman.models import Session

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation import build_cart
from shopman.storefront.presentation.cart import (
    CartItemProjection,
    CartProjection,
    MinimumOrderProgressProjection,
)

pytestmark = pytest.mark.django_db


def _request_with_cart_session(client):
    """Build a RequestFactory request wearing the session key of ``client``.

    ``cart_session`` in conftest returns a Django test client that has
    already POSTed to /cart/set-qty/. We need a plain ``HttpRequest`` whose
    ``request.session`` holds the same ``cart_session_key``; the projection
    builder reads it via ``CartService.get_cart(request)``.
    """
    rf = RequestFactory()
    request = rf.get("/carrinho/")
    request.session = client.session  # type: ignore[attr-defined]
    return request


# ──────────────────────────────────────────────────────────────────────
# Empty cart
# ──────────────────────────────────────────────────────────────────────


class TestEmptyCart:
    def test_empty_cart_has_stable_shape(self, client):
        rf = RequestFactory()
        request = rf.get("/carrinho/")
        request.session = client.session  # type: ignore[attr-defined]

        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert isinstance(proj, CartProjection)
        assert proj.is_empty is True
        assert proj.items == ()
        assert proj.items_count == 0
        assert proj.subtotal_q == 0
        assert proj.subtotal_display == "R$ 0,00"
        assert proj.grand_total_q == 0
        assert proj.has_discount is False
        assert proj.has_unavailable_items is False
        assert proj.coupon_code is None
        assert proj.minimum_order_progress is None
        assert proj.upsell is None
        checkout = next(action for action in proj.actions if action.ref == "checkout")
        assert checkout.kind == "link"
        assert checkout.enabled is False
        assert checkout.reason == "Sacola vazia."
        assert checkout.href == "/checkout"


# ──────────────────────────────────────────────────────────────────────
# Populated cart
# ──────────────────────────────────────────────────────────────────────


class TestPopulatedCart:
    def test_basic_shape(self, cart_session, product):
        # cart_session added 2x product at the resolved unit price.
        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.is_empty is False
        assert len(proj.items) == 1
        item = proj.items[0]
        assert isinstance(item, CartItemProjection)
        assert item.sku == product.sku
        assert item.name == "Pão Francês"
        assert item.qty == 2
        assert item.unit_price_q > 0
        assert item.total_price_q == item.unit_price_q * 2
        assert item.price_display.startswith("R$ ")
        assert item.total_display.startswith("R$ ")
        assert item.is_available is True
        assert item.availability_warning is None

        assert proj.items_count == 2
        assert proj.subtotal_q == item.total_price_q
        assert proj.grand_total_q == item.total_price_q
        checkout = next(action for action in proj.actions if action.ref == "checkout")
        assert checkout.label == "Finalizar pedido"
        assert checkout.href == "/checkout"
        if proj.minimum_order_progress is not None:
            assert checkout.enabled is False
            assert checkout.reason == f"Faltam {proj.minimum_order_progress.remaining_display} para o pedido mínimo."
        else:
            assert checkout.enabled is True
            assert checkout.reason == ""

    def test_projection_is_immutable(self, cart_session):
        from dataclasses import FrozenInstanceError

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        with pytest.raises(FrozenInstanceError):
            proj.items_count = 99  # type: ignore[misc]

    def test_item_is_immutable(self, cart_session):
        from dataclasses import FrozenInstanceError

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        with pytest.raises(FrozenInstanceError):
            proj.items[0].qty = 99  # type: ignore[misc]

    def test_upsell_includes_unit_price_for_surface_mutation(
        self, cart_session, croissant, monkeypatch,
    ):
        from shopman.shop.projections.cart import UpsellSuggestionProjection

        def fake_upsell(cart_skus, *, channel_ref):
            return UpsellSuggestionProjection(
                sku=croissant.sku,
                name=croissant.name,
                unit_price_q=800,
                image_url=None,
            )

        monkeypatch.setattr(
            "shopman.shop.projections.cart.build_upsell_suggestion",
            fake_upsell,
        )

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.upsell is not None
        assert proj.upsell.sku == croissant.sku
        assert proj.upsell.unit_price_q == 800
        assert proj.upsell.price_display == "R$ 8,00"


# ──────────────────────────────────────────────────────────────────────
# Availability — own-hold correction
# ──────────────────────────────────────────────────────────────────────


class TestAvailabilityOwnHoldCorrection:
    """Regression: a cart line is only flagged unavailable when the shortage
    is real (external), not when the customer's own hold is the reason
    ``total_promisable`` hit zero.

    Previously the cart compared ``total_promisable < line.qty`` without
    knowing that ``total_promisable`` excludes the session's own hold.
    A customer who bought the entire physical stock saw a sold-out warning
    next to their own N units — nonsensical.
    """

    def test_cart_holding_all_physical_stock_shows_no_warning(
        self, client, channel, product,
    ):
        """Stock=5, cart=5 (all reserved by own hold) → no warning."""
        from datetime import date
        from decimal import Decimal

        from shopman.stockman import stock
        from shopman.stockman.models import Position, PositionKind

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        _ensure_listing_item(channel, product, price_q=90)
        position, _ = Position.objects.get_or_create(
            ref="loja",
            defaults={
                "name": "Loja Principal",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )
        stock.receive(
            quantity=Decimal("5"),
            sku=product.sku,
            position=position,
            target_date=date.today(),
            reason="own-hold regression seed",
        )

        resp = client.put(
            f"/api/v1/cart/skus/{product.sku}/",
            data=json.dumps({"qty": 5}),
            content_type="application/json",
        )
        assert resp.status_code in (200, 201), (
            "adding all available stock must succeed — hold protects the qty"
        )

        request = _request_with_cart_session(client)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert len(proj.items) == 1
        item = proj.items[0]
        assert item.qty == 5
        assert item.is_available is True, (
            "session holding all its own stock must NOT be flagged unavailable"
        )
        assert item.availability_warning is None


class TestAwaitingConfirmationIsNotUnavailable:
    """Regression (incidente da baguete, 2026-07-14): linha em planned-hold
    ("Aguardando confirmação") NÃO conta como indisponível.

    Sem estoque pronto mas com produção planejada, o add cria um hold
    planejado indefinido — a falta de pronta-entrega é exatamente o que o
    selo da linha já explica. Contá-la em ``has_unavailable`` disparava o
    banner "estoque mudou" e bloqueava o checkout JUNTO do selo acolhedor:
    beco sem saída. O commit adota o hold planejado, então o checkout pode
    seguir (AVAILABILITY-PLAN §5 bloqueia só por Indisponível).
    """

    def test_planned_hold_line_does_not_raise_banner_nor_block_checkout(
        self, client, channel, product,
    ):
        from datetime import date
        from decimal import Decimal

        from shopman.stockman import stock
        from shopman.stockman.models import Position, PositionKind

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        _ensure_listing_item(channel, product, price_q=90)
        position, _ = Position.objects.get_or_create(
            ref="loja",
            defaults={
                "name": "Loja Principal",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )
        # Fornada planejada pra HOJE (quant target-dated, ainda não realizada);
        # NENHUM estoque pronto.
        stock.plan(
            quantity=Decimal("10"),
            product=product,
            target_date=date.today(),
            position=position,
            reason="fornada planejada (teste baguete)",
        )

        resp = client.put(
            f"/api/v1/cart/skus/{product.sku}/",
            data=json.dumps({"qty": 2}),
            content_type="application/json",
        )
        assert resp.status_code in (200, 201), (
            "com produção planejada, o add deve aceitar (hold planejado)"
        )

        request = _request_with_cart_session(client)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert len(proj.items) == 1
        item = proj.items[0]
        assert item.is_awaiting_confirmation is True, "linha deve estar em espera de materialização"
        assert proj.has_awaiting_confirmation_items is True
        assert proj.has_unavailable_items is False, (
            "aguardando confirmação NÃO é indisponível — banner não pode disparar"
        )
        checkout = next(action for action in proj.actions if action.ref == "checkout")
        assert checkout.reason != "Revise itens indisponíveis antes de finalizar."


# ──────────────────────────────────────────────────────────────────────
# Minimum order progress
# ──────────────────────────────────────────────────────────────────────


def _set_shop_rules(**rules_q):
    """Set ``shop.defaults.rules`` cents policies for one test."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    shop.defaults = shop.defaults or {}
    shop.defaults.setdefault("rules", {}).update(rules_q)
    shop.save(update_fields=["defaults"])


class TestMinimumOrderProgress:
    def test_progress_shown_when_minimum_set(self, cart_session):
        # Set the general minimum to R$ 50,00 (5000q); the cart is R$ 1,80 → way below.
        _set_shop_rules(minimum_order_q=5000)

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.minimum_order_progress is not None
        progress = proj.minimum_order_progress
        assert isinstance(progress, MinimumOrderProgressProjection)
        assert progress.minimum_q == 5000
        assert progress.remaining_q == 5000 - proj.subtotal_q
        assert progress.minimum_display == "R$ 50,00"
        assert 0 <= progress.percent <= 100
        checkout = next(action for action in proj.actions if action.ref == "checkout")
        assert checkout.enabled is False
        assert checkout.reason == f"Faltam {progress.remaining_display} para o pedido mínimo."

    def test_no_progress_when_minimum_off(self, cart_session):
        # 0/absent = no minimum (footgun fixed: no magic R$ 10,00 fallback).
        _set_shop_rules(minimum_order_q=0)

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert proj.minimum_order_progress is None
        checkout = next(action for action in proj.actions if action.ref == "checkout")
        assert checkout.enabled is True
        assert checkout.reason == ""


class TestDeliveryMinimumProgress:
    def test_progress_shown_when_below(self, cart_session):
        _set_shop_rules(delivery_minimum_q=5000)

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.delivery_minimum_progress is not None
        assert proj.delivery_minimum_progress.minimum_q == 5000
        # General checkout is NOT blocked by the delivery-only minimum.
        checkout = next(action for action in proj.actions if action.ref == "checkout")
        assert checkout.enabled is True

    def test_none_when_off(self, cart_session):
        _set_shop_rules(delivery_minimum_q=0)
        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert proj.delivery_minimum_progress is None

    def test_coupon_does_not_disqualify_delivery_minimum(self, cart_session):
        # Cupom promocional NÃO pode tirar a elegibilidade de entrega: o mínimo olha
        # o valor ANTES do cupom (subtotal + desconto do cupom). Bug "R$30 bloqueado".
        session = Session.objects.get(channel_ref=STOREFRONT_CHANNEL_REF, state="open")
        session.data = {**(session.data or {}), "coupon_code": "TESTE"}
        session.pricing = {"coupon": {"discount_q": 1000}}
        session.save(update_fields=["data", "pricing"])

        request = _request_with_cart_session(cart_session)
        subtotal_q = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF).subtotal_q

        # Mínimo ENTRE o subtotal e (subtotal + cupom): sem o cupom contaria como abaixo,
        # mas como o cupom é somado de volta, fica elegível (sem bloqueio).
        _set_shop_rules(delivery_minimum_q=subtotal_q + 500)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert proj.delivery_minimum_progress is None

        # Acima do valor pré-cupom também → aí sim bloqueia (sanidade).
        _set_shop_rules(delivery_minimum_q=subtotal_q + 5000)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert proj.delivery_minimum_progress is not None


class TestFreeDeliveryProgress:
    def test_progress_shown_when_below(self, cart_session):
        _set_shop_rules(free_delivery_above_q=5000)

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.free_delivery_progress is not None
        assert proj.free_delivery_progress.threshold_q == 5000
        assert proj.free_delivery_progress.remaining_q == 5000 - proj.subtotal_q

    def test_none_when_off(self, cart_session):
        _set_shop_rules(free_delivery_above_q=0)
        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        assert proj.free_delivery_progress is None


# ──────────────────────────────────────────────────────────────────────
# Discount lines
# ──────────────────────────────────────────────────────────────────────


class TestDiscounts:
    def test_discount_line_reflected(self, cart_session):
        # Inject a fake discount breakdown into the Orderman session so the
        # builder has a pricing snapshot to translate. This mirrors what
        # DiscountModifier would write during modify_session().
        session = Session.objects.get(channel_ref=STOREFRONT_CHANNEL_REF, state="open")
        session.pricing = {
            "discount": {
                "total_discount_q": 40,
                "items": [
                    {
                        "sku": "PAO-FRANCES",
                        "name": "Promoção Teste",
                        "type": "promotion",
                        "qty": 2,
                        "discount_q": 20,
                        "original_price_q": 100,
                    },
                ],
            },
        }
        session.save(update_fields=["pricing"])

        request = _request_with_cart_session(cart_session)
        proj = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)

        assert proj.has_discount is True
        assert proj.discount_total_q == 40
        assert proj.discount_total_display == "R$ 0,40"
        assert len(proj.discount_lines) == 1
        row = proj.discount_lines[0]
        assert row.label == "Promoção Teste"
        assert row.amount_q == 40
        assert row.amount_display == "R$ 0,40"
