"""AudienceResolver — favoritos, alertas, recompra, opt-in e VIP-first.

O teste mais importante deste arquivo é o do opt-in: sem consentimento
explícito, ninguém entra na audiência. Todo o resto é otimização.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.contrib.preferences.models import CustomerPreference
from shopman.guestman.models import Customer

from shopman.shop.services import audience
from shopman.storefront.models import CustomerFavorite, StockAlertSubscription

pytestmark = pytest.mark.django_db

SKU = "croissant-trad"


def _customer(
    phone: str, *, first_name: str = "Ana", opted_in: bool | None = True, ref: str = ""
) -> Customer:
    customer = Customer.objects.create(
        ref=ref or f"CLI-{phone[-4:]}", first_name=first_name, phone=phone
    )
    if opted_in is not None:
        CustomerPreference.objects.create(
            customer=customer,
            category=audience.OPTIN_CATEGORY,
            key=audience.OPTIN_KEY,
            value={"enabled": opted_in},
        )
    return customer


# ── Favoritos (F8) ───────────────────────────────────────────────────


class TestFavorites:
    def test_favorite_with_optin_is_reached(self):
        customer = _customer("+5543999990001")
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        result = audience.resolve(SKU, {"favorites": True})
        assert [r.phone for r in result.general] == [customer.phone]
        assert result.total == 1

    def test_favorite_of_another_sku_is_not_reached(self):
        customer = _customer("+5543999990001")
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku="pao-frances")

        assert audience.resolve(SKU, {"favorites": True}).total == 0

    def test_rule_off_means_no_lookup(self):
        customer = _customer("+5543999990001")
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        assert audience.resolve(SKU, {}).total == 0


# ── Opt-in (invariante) ──────────────────────────────────────────────


class TestOptIn:
    def test_without_optin_nobody_is_reached(self):
        customer = _customer("+5543999990001", opted_in=None)
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        assert audience.resolve(SKU, {"favorites": True}).total == 0

    def test_explicit_opt_out_is_respected(self):
        customer = _customer("+5543999990001", opted_in=False)
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        assert audience.resolve(SKU, {"favorites": True}).total == 0

    def test_channels_list_counts_as_optin(self):
        customer = Customer.objects.create(
            ref="CLI-0001", first_name="Ana", phone="+5543999990001"
        )
        CustomerPreference.objects.create(
            customer=customer,
            category=audience.OPTIN_CATEGORY,
            key=audience.OPTIN_KEY,
            value={"channels": ["whatsapp"]},
        )
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        assert audience.resolve(SKU, {"favorites": True}).total == 1

    def test_empty_channels_list_is_not_optin(self):
        customer = Customer.objects.create(
            ref="CLI-0001", first_name="Ana", phone="+5543999990001"
        )
        CustomerPreference.objects.create(
            customer=customer,
            category=audience.OPTIN_CATEGORY,
            key=audience.OPTIN_KEY,
            value={"channels": []},
        )
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        assert audience.resolve(SKU, {"favorites": True}).total == 0


# ── Alertas por SKU (F9) ─────────────────────────────────────────────


class TestAlerts:
    def test_subscription_is_its_own_consent(self):
        """Quem pediu para ser avisado daquele SKU já consentiu naquele SKU."""
        StockAlertSubscription.objects.create(sku=SKU, contact_phone="+5543999990002")

        result = audience.resolve(SKU, {"alerts": True})
        assert [r.phone for r in result.general] == ["+5543999990002"]

    def test_already_notified_subscription_is_skipped(self):
        StockAlertSubscription.objects.create(
            sku=SKU, contact_phone="+5543999990002", notified_at=timezone.now()
        )
        assert audience.resolve(SKU, {"alerts": True}).total == 0

    def test_subscription_without_phone_is_unreachable(self):
        StockAlertSubscription.objects.create(sku=SKU, customer_ref="CUST-1")
        assert audience.resolve(SKU, {"alerts": True}).total == 0


# ── Recompra (F10) ───────────────────────────────────────────────────


class TestRecompra:
    def _insight(self, customer, *, last_order_days_ago: int):
        last = timezone.localdate() - timedelta(days=last_order_days_ago)
        return CustomerInsight.objects.create(
            customer=customer,
            favorite_products=[{"sku": SKU, "qtd": 4, "ultimo_pedido": last.isoformat()}],
        )

    def test_recent_buyer_is_reached(self):
        customer = _customer("+5543999990003")
        self._insight(customer, last_order_days_ago=10)

        result = audience.resolve(SKU, {"recompra_days": 90})
        assert [r.phone for r in result.general] == [customer.phone]

    def test_cold_buyer_is_outside_the_window(self):
        customer = _customer("+5543999990003")
        self._insight(customer, last_order_days_ago=200)

        assert audience.resolve(SKU, {"recompra_days": 90}).total == 0

    def test_buyer_of_another_sku_is_not_reached(self):
        customer = _customer("+5543999990003")
        CustomerInsight.objects.create(
            customer=customer,
            favorite_products=[{"sku": "pao-frances", "ultimo_pedido": "2026-07-01"}],
        )
        assert audience.resolve(SKU, {"recompra_days": 90}).total == 0


# ── Dedupe ───────────────────────────────────────────────────────────


class TestDedupe:
    def test_same_phone_across_rules_receives_once(self):
        customer = _customer("+5543999990001")
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)
        StockAlertSubscription.objects.create(sku=SKU, contact_phone=customer.phone)

        result = audience.resolve(SKU, {"favorites": True, "alerts": True})
        assert result.total == 1

    def test_reasons_accumulate(self):
        customer = _customer("+5543999990001")
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)
        StockAlertSubscription.objects.create(sku=SKU, contact_phone=customer.phone)

        recipient = audience.resolve(SKU, {"favorites": True, "alerts": True}).general[0]
        assert recipient.reasons == frozenset({"favorites", "alerts"})

    def test_counts_report_each_rule_before_dedupe(self):
        customer = _customer("+5543999990001")
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)
        StockAlertSubscription.objects.create(sku=SKU, contact_phone=customer.phone)

        summary = audience.resolve(SKU, {"favorites": True, "alerts": True}).summary()
        assert summary["favorites_count"] == 1
        assert summary["alerts_count"] == 1
        assert summary["total"] == 1


# ── VIP first (F11) ──────────────────────────────────────────────────


class TestVipFirst:
    def _vip(self, phone: str) -> Customer:
        customer = _customer(phone, first_name="Vip")
        CustomerInsight.objects.create(customer=customer, rfm_segment="champion")
        return customer

    def test_vips_are_split_into_their_own_wave(self):
        vip = self._vip("+5543999990010")
        plain = _customer("+5543999990011", first_name="Comum")
        for customer in (vip, plain):
            CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        result = audience.resolve(SKU, {"favorites": True, "vip_first_minutes": 15})
        assert [r.phone for r in result.vip] == [vip.phone]
        assert [r.phone for r in result.general] == [plain.phone]
        assert result.vip_delay_minutes == 15

    def test_everyone_is_still_reached(self):
        vip = self._vip("+5543999990010")
        plain = _customer("+5543999990011", first_name="Comum")
        for customer in (vip, plain):
            CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        result = audience.resolve(SKU, {"favorites": True, "vip_first_minutes": 15})
        assert result.total == 2
        assert result.all_recipients()[0].phone == vip.phone  # VIP na frente

    def test_without_delay_there_is_a_single_wave(self):
        self._vip("+5543999990010")
        CustomerFavorite.objects.create(
            customer_ref=Customer.objects.get(phone="+5543999990010").ref, sku=SKU
        )
        result = audience.resolve(SKU, {"favorites": True})
        assert result.vip == ()
        assert len(result.general) == 1

    def test_loyalty_tier_also_grants_vip(self):
        from shopman.guestman.contrib.loyalty.models import LoyaltyAccount

        customer = _customer("+5543999990012", first_name="Ouro")
        LoyaltyAccount.objects.create(customer=customer, tier="gold")
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        result = audience.resolve(SKU, {"favorites": True, "vip_first_minutes": 10})
        assert [r.phone for r in result.vip] == [customer.phone]


# ── Resumo ───────────────────────────────────────────────────────────


class TestSummary:
    def test_summary_carries_no_pii(self):
        customer = _customer("+5543999990001")
        CustomerFavorite.objects.create(customer_ref=customer.ref, sku=SKU)

        summary = audience.resolve(SKU, {"favorites": True}).summary()
        assert customer.phone not in str(summary)
        assert summary["total"] == 1

    def test_empty_audience_is_a_normal_answer(self):
        result = audience.resolve(SKU, {"favorites": True, "alerts": True})
        assert result.total == 0
        assert result.summary()["total"] == 0
