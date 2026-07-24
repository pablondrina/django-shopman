"""Lead time no checkout — a data escolhida respeita a antecedência por SKU.

Política do dono (Pablo, 2026-07-24): "o registro de demanda só pode ocorrer
dentro do prazo do lead time". No checkout, cada SKU do carrinho exige
``delivery_date >= earliest_allowed_date`` — com mensagem omotenashi apontando
a primeira data possível (nome do produto, nunca SKU cru). O gate vale só para
DEMANDA: fornada planejada para a data (Quant planejado) e venda do estoque
físico de hoje passam direto.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from shopman.storefront.intents.checkout import _validate_preorder

SKU = "CHECKOUT-LEAD-SKU"
LEAD_HOURS = 48


def _make_product(sku: str = SKU, *, lead_time_hours: int | None = LEAD_HOURS):
    from shopman.offerman.models import Product

    product = Product.objects.create(
        sku=sku,
        name="Pain de Campagne",
        base_price_q=1800,
        shelf_life_days=0,
        is_published=True,
        is_sellable=True,
    )
    if lead_time_hours is not None:
        product.metadata = {**(product.metadata or {}), "lead_time_hours": lead_time_hours}
        product.save(update_fields=["metadata"])
    return product


def _line(sku: str = SKU, *, name: str = "Pain de Campagne", qty: int = 2):
    return SimpleNamespace(sku=sku, name=name, qty=qty)


class CheckoutLeadTimeTests(TestCase):
    def setUp(self):
        from shopman.shop.models import Channel, Shop

        Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
        self.channel = Channel.objects.create(
            ref="lead-checkout-web", name="web", is_active=True, config={}
        )
        self.product = _make_product()

        from shopman.stockman.models import Position, PositionKind

        self.vitrine = Position.objects.get_or_create(
            ref="lead-checkout-vitrine",
            defaults={"name": "vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
        )[0]

        from shopman.shop.services import lead_time

        self.tomorrow = timezone.localdate() + timedelta(days=1)
        self.earliest = lead_time.earliest_allowed_date(SKU, self.channel.ref)
        # Lead de 48h ⇒ a primeira data possível é sempre depois de amanhã.
        assert self.earliest > self.tomorrow

    def _receive_today(self, qty: int = 5):
        from shopman.stockman import stock

        stock.receive(Decimal(str(qty)), SKU, self.vitrine, reason="lead checkout setup")

    def _plan(self, qty: int, target_date):
        from shopman.stockman.service import Stock

        Stock.plan(Decimal(str(qty)), self.product, target_date)

    def _validate(self, chosen_date):
        return _validate_preorder(
            chosen_date.isoformat(),
            cart_lines=[_line()],
            channel_ref=self.channel.ref,
            session_key="",
        )

    def test_date_before_lead_time_blocked_with_first_possible_date(self) -> None:
        errors = self._validate(self.tomorrow)

        self.assertIn("delivery_date", errors)
        message = errors["delivery_date"]
        self.assertIn("Pain de Campagne", message)  # nome, não SKU cru
        self.assertNotIn(SKU, message)
        self.assertIn(f"{LEAD_HOURS}h de antecedência", message)
        self.assertIn(self.earliest.strftime("%d/%m"), message)

    def test_earliest_allowed_date_passes(self) -> None:
        errors = self._validate(self.earliest)
        self.assertNotIn("delivery_date", errors)

    def test_planned_batch_for_the_date_passes_despite_lead_time(self) -> None:
        """Fornada planejada para amanhã honra o compromisso — sem bloqueio."""
        self._plan(5, self.tomorrow)
        errors = self._validate(self.tomorrow)
        self.assertNotIn("delivery_date", errors)

    def test_today_with_physical_stock_never_blocked(self) -> None:
        """Data de hoje = venda do estoque físico presente; lead time não vale."""
        self._receive_today()
        errors = self._validate(timezone.localdate())
        self.assertNotIn("delivery_date", errors)

    def test_product_without_lead_time_unaffected(self) -> None:
        from shopman.offerman.models import Product

        Product.objects.create(
            sku="CHECKOUT-PLAIN-SKU",
            name="Baguete",
            base_price_q=900,
            is_published=True,
            is_sellable=True,
        )
        errors = _validate_preorder(
            self.tomorrow.isoformat(),
            cart_lines=[_line("CHECKOUT-PLAIN-SKU", name="Baguete", qty=1)],
            channel_ref=self.channel.ref,
            session_key="",
        )
        self.assertNotIn("delivery_date", errors)


class LeadTimeHelperTests(TestCase):
    """Contrato do helper único (shop/services/lead_time.py)."""

    def setUp(self):
        from shopman.shop.models import Channel, Shop

        Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
        self.channel = Channel.objects.create(
            ref="lead-helper-web", name="web", is_active=True,
            config={"stock": {"default_lead_time_hours": 12}},
        )

    def test_product_metadata_wins_over_channel_default(self) -> None:
        from shopman.shop.services import lead_time

        _make_product("HELPER-LEAD-SKU", lead_time_hours=24)
        self.assertEqual(
            lead_time.effective_lead_time_hours("HELPER-LEAD-SKU", self.channel.ref), 24
        )

    def test_channel_default_used_when_product_silent(self) -> None:
        from shopman.shop.services import lead_time

        _make_product("HELPER-PLAIN-SKU", lead_time_hours=None)
        self.assertEqual(
            lead_time.effective_lead_time_hours("HELPER-PLAIN-SKU", self.channel.ref), 12
        )
        # SKU desconhecido também cai no default do canal.
        self.assertEqual(
            lead_time.effective_lead_time_hours("HELPER-GHOST-SKU", self.channel.ref), 12
        )

    def test_earliest_allowed_date_rounds_up_to_next_batch_day(self) -> None:
        """Lead precisa estar COMPLETO antes da fornada da data começar:
        24/07 15h + 24h = 25/07 15h → a fornada de 25/07 já começou → 26/07."""
        from shopman.shop.services import lead_time

        _make_product("HELPER-ROUND-SKU", lead_time_hours=24)
        tz = timezone.get_current_timezone()
        afternoon = datetime(2026, 7, 24, 15, 0, tzinfo=tz)
        self.assertEqual(
            lead_time.earliest_allowed_date("HELPER-ROUND-SKU", self.channel.ref, afternoon),
            datetime(2026, 7, 26).date(),
        )
        # Exatamente à meia-noite o lead fecha junto com a virada — 25/07 vale.
        midnight = datetime(2026, 7, 24, 0, 0, tzinfo=tz)
        self.assertEqual(
            lead_time.earliest_allowed_date("HELPER-ROUND-SKU", self.channel.ref, midnight),
            datetime(2026, 7, 25).date(),
        )

    def test_zero_lead_time_means_today(self) -> None:
        from shopman.shop.services import lead_time

        _make_product("HELPER-ZERO-SKU", lead_time_hours=0)
        self.assertEqual(
            lead_time.earliest_allowed_date("HELPER-ZERO-SKU", self.channel.ref),
            timezone.localdate(),
        )

    def test_config_validation_rejects_bad_values(self) -> None:
        from shopman.shop.config import ChannelConfig

        bad_untracked = ChannelConfig()
        bad_untracked.stock.allow_untracked = "nope"
        with self.assertRaises(ValueError):
            bad_untracked.validate()

        bad_lead = ChannelConfig()
        bad_lead.stock.default_lead_time_hours = -1
        with self.assertRaises(ValueError):
            bad_lead.validate()
