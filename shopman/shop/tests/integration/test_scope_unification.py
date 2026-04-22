"""
Scope unification regression — trava o contrato ``check == reserve``.

Para qualquer SKU × canal × qty, a qty máxima que ``availability.check``
promete precisa ser exatamente a qty que ``availability.reserve`` consegue
holdar. Isso evita o bug em que o modal de shortage mostrava N disponíveis,
o cliente clicava "aceitar N", e o servidor voltava 422 porque o reserve
não conseguia colocar holds suficientes.

Cobre também a regra de D-1 (posição ``ontem`` é staff-only: canais remotos
não veem, PDV vê).
"""

from decimal import Decimal

import pytest
from shopman.shop.services import availability
from shopman.stockman.services.movements import StockMovements

pytestmark = pytest.mark.django_db


@pytest.fixture
def position_ontem(db):
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="ontem",
        defaults={
            "name": "Vitrine D-1",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return position


@pytest.fixture
def web_channel(db):
    from shopman.shop.models import Channel

    channel, _ = Channel.objects.update_or_create(
        ref="web",
        defaults={
            "name": "E-commerce",
            "kind": "web",
            "is_active": True,
            "config": {"stock": {"excluded_positions": ["ontem"]}},
        },
    )
    return channel


@pytest.fixture
def pdv_channel(db):
    from shopman.shop.models import Channel

    channel, _ = Channel.objects.update_or_create(
        ref="pdv",
        defaults={
            "name": "Balcão / PDV",
            "kind": "pos",
            "is_active": True,
            "config": {"stock": {}},
        },
    )
    return channel


class TestScopeUnification:
    """``check(sku, qty, channel)['available_qty']`` equals the qty that
    ``reserve(sku, qty, channel)`` is actually able to hold."""

    def test_remote_channel_excludes_ontem(
        self, product, position_loja, position_ontem, web_channel,
    ):
        """Web channel with excluded_positions=['ontem'] must not count
        quants at that position."""
        StockMovements.receive(
            Decimal("5"), product.sku, position=position_loja,
            reason="Produção fresca",
        )
        StockMovements.receive(
            Decimal("7"), product.sku, position=position_ontem,
            reason="D-1 markdown",
        )

        check_result = availability.check(
            product.sku, Decimal("12"), channel_ref="web",
        )
        assert check_result["available_qty"] == Decimal("5")

    def test_staff_channel_sees_ontem(
        self, product, position_loja, position_ontem, pdv_channel,
    ):
        """PDV (staff) without excluded_positions must count all
        saleable positions, including ontem."""
        StockMovements.receive(
            Decimal("5"), product.sku, position=position_loja,
            reason="Produção fresca",
        )
        StockMovements.receive(
            Decimal("7"), product.sku, position=position_ontem,
            reason="D-1 markdown",
        )

        check_result = availability.check(
            product.sku, Decimal("12"), channel_ref="pdv",
        )
        assert check_result["available_qty"] == Decimal("12")

    def test_check_and_reserve_agree_for_fragmented_stock(
        self, product, position_loja, position_ontem, web_channel,
    ):
        """Fragmented stock across quants: the qty reported by check must
        be exactly what reserve can deliver (including fallback across quants).

        Previously, check returned the total across all visible positions while
        reserve, restricted to a single quant at a time, would fall back to the
        split-across-quants path and could fail. With the canonical scope gate
        the two views are forced to agree.
        """
        StockMovements.receive(
            Decimal("10"), product.sku, position=position_loja,
            reason="Lote manhã",
        )
        StockMovements.receive(
            Decimal("4"), product.sku, position=position_ontem,
            reason="D-1 (staff-only)",
        )

        check = availability.check(
            product.sku, Decimal("99"), channel_ref="web",
        )
        promised = check["available_qty"]
        assert promised == Decimal("10")

        reserve = availability.reserve(
            product.sku, promised, session_key="test-session",
            channel_ref="web",
        )
        assert reserve["ok"] is True
        assert reserve["available_qty"] == promised

    def test_reserve_never_holds_on_excluded_position(
        self, product, position_ontem, web_channel,
    ):
        """Remote channel: if the only available stock is at ``ontem``,
        reserve must refuse — matching check, which returns 0 visible."""
        StockMovements.receive(
            Decimal("10"), product.sku, position=position_ontem,
            reason="D-1",
        )

        check = availability.check(
            product.sku, Decimal("1"), channel_ref="web",
        )
        assert check["ok"] is False
        assert check["available_qty"] == Decimal("0")

        reserve = availability.reserve(
            product.sku, Decimal("1"), session_key="test-session",
            channel_ref="web",
        )
        assert reserve["ok"] is False

    def test_staff_channel_can_reserve_ontem(
        self, product, position_ontem, pdv_channel,
    ):
        """PDV reserves at ontem normally — the denylist is a per-channel
        scoping concern, not a global rule."""
        StockMovements.receive(
            Decimal("10"), product.sku, position=position_ontem,
            reason="D-1",
        )

        reserve = availability.reserve(
            product.sku, Decimal("3"), session_key="test-session",
            channel_ref="pdv",
        )
        assert reserve["ok"] is True
