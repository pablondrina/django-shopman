"""Tests for shopman.admin — admin registration, extensions, and dashboard."""

from __future__ import annotations

import json
from datetime import date, time

import pytest
from django import forms
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.urls import NoReverseMatch, reverse

from shopman.backstage.models import DayClosing, KDSInstance, OperatorAlert
from shopman.shop.models import (
    RuleConfig,
    Shop,
)

# ── Helpers ──────────────────────────────────────────────────────────


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("admin", "admin@test.com", "pass")


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def shop(db):
    return Shop.objects.create(
        name="Test Shop",
        brand_name="Test",
        short_name="TS",
        primary_color="#C5A55A",
        default_ddd="43",
    )


def _shop_form_data(shop):
    """Build POST data for ShopForm as a QueryDict (mirrors real admin POST).

    ArrayWidget fields (social_links) bind via ``getlist`` → precisam de QueryDict
    com multi-valor, não de um dict simples.
    """
    from django.http import QueryDict

    from shopman.shop.admin.shop import ShopForm

    initial_form = ShopForm(instance=shop)
    data = {}
    list_fields = {"social_links"}  # ArrayWidget → lista de valores
    json_object_fields = {"tracking_copy", "integrations"}

    for name, field in initial_form.fields.items():
        if name == "logo":
            data[name] = ""
            continue
        value = initial_form.initial.get(name)
        if value is None:
            value = field.initial
        if value is None and hasattr(shop, name):
            value = getattr(shop, name)
        if name in list_fields:
            data[name] = list(value or [])
            continue
        if name in json_object_fields:
            data[name] = json.dumps(value or {})
            continue
        if isinstance(field, forms.MultipleChoiceField):
            data[name] = list(value or [])
        elif isinstance(value, time):
            data[name] = value.strftime("%H:%M")
        elif isinstance(value, date):
            data[name] = value.isoformat()
        elif isinstance(value, (dict, list)):
            data[name] = json.dumps(value)
        elif value is None:
            data[name] = ""
        else:
            data[name] = value

    query = QueryDict(mutable=True)
    for name, value in data.items():
        if isinstance(value, list):
            query.setlist(name, value)
        else:
            query[name] = value
    return query


# ── Registration tests ──────────────────────────────────────────────


class TestAdminRegistration:
    """All shopman models are registered in the admin."""

    def test_shop_registered(self, db):
        assert Shop in admin.site._registry

    def test_operator_alert_registered(self, db):
        assert OperatorAlert in admin.site._registry

    def test_kds_instance_registered(self, db):
        assert KDSInstance in admin.site._registry

    def test_day_closing_registered(self, db):
        assert DayClosing in admin.site._registry

    def test_rule_config_registered(self, db):
        assert RuleConfig in admin.site._registry


# ── Shop singleton behavior ─────────────────────────────────────────


class TestShopAdminStorefrontPreview:
    """WP-S4 — iframe preview no change do Shop."""

    def test_readonly_fields_include_storefront_preview(self, db):
        from shopman.shop.models import ShopAppearance

        appearance_admin = admin.site._registry[ShopAppearance]
        assert "storefront_preview" in (appearance_admin.readonly_fields or ())

    def test_change_page_contains_preview_iframe(self, db, admin_user, shop):
        client = Client()
        client.force_login(admin_user)
        url = reverse("admin:shop_shopappearance_change", args=[shop.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"storefront-preview-iframe" in resp.content
        assert b"Atualizar preview" in resp.content


class TestShopAdminOpeningHours:
    def test_change_page_uses_structured_opening_hour_fields(self, db, admin_user, shop):
        client = Client()
        client.force_login(admin_user)
        url = reverse("admin:shop_shopoperation_change", args=[shop.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert b'name="opening_hours_wednesday_status"' in resp.content
        assert b'name="opening_hours_wednesday_open"' in resp.content
        assert b'name="opening_hours_wednesday_close"' in resp.content
        assert b'name="opening_hours"' not in resp.content

    def test_form_saves_opening_hours_from_day_fields(self, shop):
        from shopman.shop.admin.shop import ShopForm

        shop.opening_hours = {
            "wednesday": {"open": "09:00", "close": "23:00"},
        }
        shop.save(update_fields=["opening_hours"])

        data = _shop_form_data(shop)

        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday"):
            data[f"opening_hours_{day}_status"] = "open"
            data[f"opening_hours_{day}_open"] = "09:00"
            data[f"opening_hours_{day}_close"] = "18:00"
        data["opening_hours_sunday_status"] = "closed"
        data["opening_hours_sunday_open"] = ""
        data["opening_hours_sunday_close"] = ""

        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()

        assert saved.opening_hours["wednesday"] == {"open": "09:00", "close": "18:00"}
        assert saved.opening_hours["saturday"] == {"open": "09:00", "close": "18:00"}
        assert "sunday" not in saved.opening_hours


class TestShopAdminDefaults:
    def test_structured_defaults_fields_live_on_focused_pages(self, db, admin_user, shop):
        client = Client()
        client.force_login(admin_user)
        # Cada domínio na sua própria página (proxy), não num scroll único.
        pages = {
            "shop_shopmenu_change": b'name="defaults_dynamic_collection_1"',
            "shop_shopordering_change": b'name="defaults_pickup_slot_1_ref"',
            "shop_shopoperation_change": b'name="defaults_closed_date_1_date"',
        }
        for url_name, field in pages.items():
            resp = client.get(reverse(f"admin:{url_name}", args=[shop.pk]))
            assert resp.status_code == 200, url_name
            assert field in resp.content, url_name
            assert b'name="defaults"' not in resp.content, url_name
        # A página base (Loja & contato) não carrega os defaults.
        base = client.get(reverse("admin:shop_shop_change", args=[shop.pk]))
        assert b'name="defaults_pickup_slot_1_ref"' not in base.content

    def test_form_saves_defaults_from_structured_fields(self, shop):
        from shopman.shop.admin.shop import ShopForm

        shop.defaults = {
            "surface_policy": {"keep": True},
            "menu": {"dynamic_collections": ["featured"]},
            "notifications": {"backend": "console", "other": "kept"},
            "pickup_slots": [
                {"ref": "slot-legacy", "label": "Legado", "starts_at": "07:00"},
                {"ref": "slot-extra-1", "label": "Extra 1", "starts_at": "19:00"},
                {"ref": "slot-extra-2", "label": "Extra 2", "starts_at": "20:00"},
                {"ref": "slot-extra-3", "label": "Extra 3", "starts_at": "21:00"},
                {"ref": "slot-extra-4", "label": "Extra 4", "starts_at": "22:00"},
                {"ref": "slot-preserved", "label": "Preservado", "starts_at": "23:00"},
            ],
            "pickup_slot_config": {"rounding_minutes": 15, "history_days": 10, "other": "kept"},
            "closed_dates": [
                {"date": "2026-12-25", "label": "Natal antigo"},
                {"from": "2026-01-02", "to": "2026-01-05", "label": "Férias"},
            ],
            "seasons": {"hot": [12, 1], "mild": [4], "cold": [7]},
            "high_demand_multiplier": "1.20",
            "safety_stock_percent": "0.20",
        }
        shop.save(update_fields=["defaults"])

        data = _shop_form_data(shop)
        data["defaults_dynamic_collection_1"] = "featured"
        data["defaults_dynamic_collection_2"] = "fresh_from_oven"
        data["defaults_dynamic_collection_3"] = "new_arrivals"
        data["defaults_dynamic_collection_4"] = ""
        data["defaults_dynamic_collection_5"] = ""
        data["defaults_notifications_backend"] = "manychat"
        data["defaults_max_preorder_days"] = "21"
        data["defaults_pickup_rounding_minutes"] = "30"
        data["defaults_pickup_history_days"] = "45"
        data["defaults_pickup_fallback_slot"] = "slot-09"
        data["defaults_pickup_slot_1_ref"] = "slot-09"
        data["defaults_pickup_slot_1_label"] = "A partir das 09h"
        data["defaults_pickup_slot_1_starts_at"] = "09:00"
        data["defaults_pickup_slot_2_ref"] = "slot-12"
        data["defaults_pickup_slot_2_label"] = "A partir das 12h"
        data["defaults_pickup_slot_2_starts_at"] = "12:00"
        data["defaults_closed_date_1_date"] = "2026-12-25"
        data["defaults_closed_date_1_label"] = "Natal"
        data["defaults_season_hot_months"] = "10, 11, 12, 1, 2, 3"
        data["defaults_season_mild_months"] = "4, 5, 9"
        data["defaults_season_cold_months"] = "6, 7, 8"
        data["defaults_high_demand_multiplier"] = "1.30"
        data["defaults_safety_stock_percent"] = "0.15"

        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()

        assert saved.defaults["surface_policy"] == {"keep": True}
        assert saved.defaults["menu"]["dynamic_collections"] == [
            "featured",
            "fresh_from_oven",
            "new_arrivals",
        ]
        assert saved.defaults["notifications"] == {"backend": "manychat", "other": "kept"}
        assert saved.defaults["max_preorder_days"] == 21
        assert saved.defaults["pickup_slots"][:2] == [
            {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
            {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
        ]
        assert saved.defaults["pickup_slots"][-1] == {
            "ref": "slot-preserved",
            "label": "Preservado",
            "starts_at": "23:00",
        }
        assert saved.defaults["pickup_slot_config"] == {
            "rounding_minutes": 30,
            "history_days": 45,
            "other": "kept",
            "fallback_slot": "slot-09",
        }
        assert saved.defaults["closed_dates"] == [
            {"date": "2026-12-25", "label": "Natal"},
            {"from": "2026-01-02", "to": "2026-01-05", "label": "Férias"},
        ]
        assert saved.defaults["seasons"] == {
            "hot": [10, 11, 12, 1, 2, 3],
            "mild": [4, 5, 9],
            "cold": [6, 7, 8],
        }
        assert saved.defaults["high_demand_multiplier"] == "1.30"
        assert saved.defaults["safety_stock_percent"] == "0.15"


class TestShopAdminLoyaltyDefaults:
    """WP-1 — fidelidade editável como campos estruturados no ShopForm."""

    def test_change_page_uses_structured_loyalty_fields(self, db, admin_user, shop):
        client = Client()
        client.force_login(admin_user)
        resp = client.get(reverse("admin:shop_shoployalty_change", args=[shop.pk]))
        assert resp.status_code == 200
        assert b'name="defaults_loyalty_points_per_real"' in resp.content
        assert b'name="defaults_loyalty_stamps_target"' in resp.content
        assert b'name="defaults_loyalty_tier_silver_threshold"' in resp.content
        assert b'name="defaults_loyalty_tier_platinum_threshold"' in resp.content

    def test_initial_reflects_existing_loyalty_block(self, shop):
        from shopman.shop.admin.shop import ShopForm

        shop.defaults = {"loyalty": {"points_per_real": 3, "stamps_target": 8, "tiers": [
            {"name": "bronze", "threshold": 0},
            {"name": "silver", "threshold": 250},
        ]}}
        shop.save(update_fields=["defaults"])

        form = ShopForm(instance=shop)
        assert form.fields["defaults_loyalty_points_per_real"].initial == 3
        assert form.fields["defaults_loyalty_stamps_target"].initial == 8
        assert form.fields["defaults_loyalty_tier_silver_threshold"].initial == 250
        # Tier ausente no bloco fica vazio.
        assert form.fields["defaults_loyalty_tier_gold_threshold"].initial is None

    def test_form_saves_loyalty_from_structured_fields(self, shop):
        from shopman.shop.admin.shop import ShopForm

        data = _shop_form_data(shop)
        data["defaults_loyalty_points_per_real"] = "2"
        data["defaults_loyalty_stamps_target"] = "12"
        data["defaults_loyalty_tier_silver_threshold"] = "400"
        data["defaults_loyalty_tier_gold_threshold"] = "1800"
        data["defaults_loyalty_tier_platinum_threshold"] = "4000"

        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()

        assert saved.defaults["loyalty"] == {
            "points_per_real": 2,
            "stamps_target": 12,
            "tiers": [
                {"name": "bronze", "threshold": 0},
                {"name": "silver", "threshold": 400},
                {"name": "gold", "threshold": 1800},
                {"name": "platinum", "threshold": 4000},
            ],
        }

    def test_non_ascending_tiers_rejected(self, shop):
        from shopman.shop.admin.shop import ShopForm

        data = _shop_form_data(shop)
        data["defaults_loyalty_tier_silver_threshold"] = "2000"
        data["defaults_loyalty_tier_gold_threshold"] = "1000"  # menor que prata → erro
        data["defaults_loyalty_tier_platinum_threshold"] = "5000"

        form = ShopForm(data=data, instance=shop)
        assert not form.is_valid()
        assert "defaults_loyalty_tier_gold_threshold" in form.errors


class TestGuestmanLoyaltyAdminUnfold:
    """WP-4 — admins guestman config-adjacentes ficam em Unfold (guarda)."""

    def test_loyalty_and_group_admins_are_unfold(self, db):
        from shopman.guestman.contrib.loyalty.models import (
            LoyaltyAccount,
            LoyaltyTransaction,
        )
        from shopman.guestman.models import CustomerGroup
        from unfold.admin import ModelAdmin as UnfoldModelAdmin

        for model in (LoyaltyAccount, LoyaltyTransaction, CustomerGroup):
            registered = admin.site._registry.get(model)
            assert registered is not None, f"{model.__name__} não registrado"
            assert isinstance(registered, UnfoldModelAdmin), (
                f"{model.__name__} não está em Unfold: "
                f"{type(registered).__module__}"
            )


class TestPosDiscountThresholdPolicy:
    """WP-5 — limiar de aprovação de desconto do PDV vira política da loja."""

    def test_form_saves_threshold_to_pos_defaults(self, shop):
        from shopman.shop.admin.shop import ShopForm

        data = _shop_form_data(shop)
        data["defaults_pos_discount_approval_threshold_q"] = "5.00"
        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.defaults["pos"]["discount_approval_threshold_q"] == 500

    def test_blank_inherits_deploy_default(self, shop):
        from shopman.shop.admin.shop import ShopForm

        shop.defaults = {"pos": {"discount_approval_threshold_q": 500}}
        shop.save(update_fields=["defaults"])
        data = _shop_form_data(shop)
        data["defaults_pos_discount_approval_threshold_q"] = ""
        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert "pos" not in saved.defaults

    def test_resolver_prefers_shop_then_setting(self, shop, settings):
        from django.core.cache import cache

        from shopman.backstage.projections.pos import _discount_approval_threshold_q
        from shopman.shop.models import Shop

        settings.SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q = 1000
        # Sem bloco pos → herda deploy default.
        Shop.objects.update(defaults={})
        cache.clear()
        assert _discount_approval_threshold_q() == 1000

        shop.defaults = {"pos": {"discount_approval_threshold_q": 0}}
        shop.save()
        cache.clear()
        # 0 é valor explícito (todo desconto exige aprovação), não "ausente".
        assert _discount_approval_threshold_q() == 0


class TestStockAlertCooldownPolicy:
    """WP-5b — cooldown de alerta de estoque vira política da loja."""

    def test_form_saves_cooldown_to_stock_alerts(self, shop):
        from shopman.shop.admin.shop import ShopForm

        data = _shop_form_data(shop)
        data["defaults_stock_alert_cooldown_minutes"] = "120"
        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.defaults["stock_alerts"]["cooldown_minutes"] == 120

    def test_blank_inherits_deploy_default(self, shop):
        from shopman.shop.admin.shop import ShopForm

        shop.defaults = {"stock_alerts": {"cooldown_minutes": 30}}
        shop.save(update_fields=["defaults"])
        data = _shop_form_data(shop)
        data["defaults_stock_alert_cooldown_minutes"] = ""
        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert "stock_alerts" not in saved.defaults

    def test_resolver_reads_shop_then_setting(self, shop, settings):
        from django.core.cache import cache
        from shopman.stockman.contrib.alerts.conf import get_alert_cooldown_minutes

        from shopman.shop.models import Shop

        settings.STOCKMAN_ALERT_COOLDOWN_MINUTES = 90
        # Sem bloco → herda deploy default.
        Shop.objects.update(defaults={})
        cache.clear()
        assert get_alert_cooldown_minutes() == 90

        shop.defaults = {"stock_alerts": {"cooldown_minutes": 15}}
        shop.save()
        cache.clear()
        assert get_alert_cooldown_minutes() == 15


class TestRuleConfigTypedParams:
    """WP-3 — params de regras conhecidas editados como campos tipados."""

    @pytest.fixture
    def happy_hour_rule(self, db):
        return RuleConfig.objects.create(
            code="happy_hour",
            rule_path="shopman.shop.rules.pricing.HappyHourRule",
            label="Hora da Xepa",
            params={"discount_percent": 25, "start": "17:30", "end": "18:00"},
            priority=65,
        )

    def test_form_exposes_typed_fields_for_known_rule(self, happy_hour_rule):
        from shopman.shop.admin.rules import RuleConfigForm

        form = RuleConfigForm(instance=happy_hour_rule)
        assert "params" not in form.fields
        assert form.fields["param_discount_percent"].initial == 25
        assert form.fields["param_start"].initial == "17:30"
        assert form.fields["param_end"].initial == "18:00"

    def test_form_saves_typed_fields_back_to_params(self, happy_hour_rule):
        from shopman.shop.admin.rules import RuleConfigForm

        data = {
            "code": "happy_hour",
            "rule_path": "shopman.shop.rules.pricing.HappyHourRule",
            "label": "Hora da Xepa",
            "enabled": "on",
            "priority": "65",
            "param_discount_percent": "30",
            "param_start": "17:00",
            "param_end": "19:00",
        }
        form = RuleConfigForm(data=data, instance=happy_hour_rule)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.params == {"discount_percent": 30, "start": "17:00", "end": "19:00"}

    def test_form_preserves_extra_param_keys(self, db):
        from shopman.shop.admin.rules import RuleConfigForm

        rule = RuleConfig.objects.create(
            code="employee_discount",
            rule_path="shopman.shop.rules.pricing.EmployeeRule",
            label="Desconto Funcionário",
            params={"discount_percent": 20, "group": "staff"},
            priority=60,
        )
        data = {
            "code": "employee_discount",
            "rule_path": "shopman.shop.rules.pricing.EmployeeRule",
            "label": "Desconto Funcionário",
            "enabled": "on",
            "priority": "60",
            "param_discount_percent": "15",
        }
        form = RuleConfigForm(data=data, instance=rule)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.params == {"discount_percent": 15, "group": "staff"}

    def test_happy_hour_rejects_inverted_window(self, happy_hour_rule):
        from shopman.shop.admin.rules import RuleConfigForm

        data = {
            "code": "happy_hour",
            "rule_path": "shopman.shop.rules.pricing.HappyHourRule",
            "label": "Hora da Xepa",
            "enabled": "on",
            "priority": "65",
            "param_discount_percent": "25",
            "param_start": "19:00",
            "param_end": "17:00",
        }
        form = RuleConfigForm(data=data, instance=happy_hour_rule)
        assert not form.is_valid()
        assert "param_end" in form.errors

    def test_unknown_rule_keeps_raw_json_params(self, db):
        from shopman.shop.admin.rules import RuleConfigForm

        rule = RuleConfig.objects.create(
            code="business_hours",
            rule_path="shopman.shop.rules.validation.BusinessHoursRule",
            label="Horário de Funcionamento",
            params={},
            priority=10,
        )
        form = RuleConfigForm(instance=rule)
        assert "params" in form.fields
        assert "param_discount_percent" not in form.fields


class TestSocialLinksArrayWidget:
    """WP-8 — social_links editado como lista (ArrayWidget), persiste lista."""

    def test_roundtrip_saves_list(self, shop):
        from shopman.shop.admin.shop import ShopForm

        data = _shop_form_data(shop)
        data.setlist("social_links", [
            "https://instagram.com/nelson",
            "https://wa.me/5543999998888",
        ])
        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.social_links == [
            "https://instagram.com/nelson",
            "https://wa.me/5543999998888",
        ]

    def test_empty_saves_empty_list(self, shop):
        from shopman.shop.admin.shop import ShopForm

        data = _shop_form_data(shop)
        data.setlist("social_links", [])
        form = ShopForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.social_links == []


class TestProxyPagesIsolation:
    """WP-7 — salvar uma página focada NÃO apaga os outros domínios."""

    def test_saving_loyalty_page_preserves_pos_and_rules(self, shop):
        from shopman.shop.admin.shop import _LOYALTY_FIELDSETS, _section_form

        shop.defaults = {
            "loyalty": {"points_per_real": 1, "stamps_target": 10,
                        "tiers": [{"name": "bronze", "threshold": 0}]},
            "pos": {"discount_approval_threshold_q": 500},
            "rules": {"minimum_order_q": 1500},
        }
        shop.save(update_fields=["defaults"])

        LoyaltyForm = _section_form(_LOYALTY_FIELDSETS)
        bound = LoyaltyForm(instance=shop)
        # só os campos de fidelidade existem nesta página
        assert "defaults_pos_discount_approval_threshold_q" not in bound.fields
        data = {
            name: ("" if field.initial is None else field.initial)
            for name, field in bound.fields.items()
        }
        data["defaults_loyalty_points_per_real"] = "3"

        form = LoyaltyForm(data=data, instance=shop)
        assert form.is_valid(), form.errors
        saved = form.save()

        assert saved.defaults["loyalty"]["points_per_real"] == 3
        # Outros domínios intactos.
        assert saved.defaults["pos"]["discount_approval_threshold_q"] == 500
        assert saved.defaults["rules"]["minimum_order_q"] == 1500

    def test_proxy_pages_registered(self, db):
        from shopman.shop.models import (
            ShopAppearance,
            ShopIntegrations,
            ShopLoyalty,
            ShopMenu,
            ShopOperation,
            ShopOrdering,
            ShopPos,
            ShopProduction,
        )

        for model in (
            ShopAppearance, ShopOperation, ShopMenu, ShopOrdering,
            ShopLoyalty, ShopPos, ShopProduction, ShopIntegrations,
        ):
            assert model in admin.site._registry


class TestShopAdminSingleton:
    def test_has_add_permission_when_empty(self, db, rf, admin_user):
        shop_admin = admin.site._registry[Shop]
        request = rf.get("/admin/shopman/shop/")
        request.user = admin_user
        assert shop_admin.has_add_permission(request) is True

    def test_has_add_permission_when_exists(self, shop, rf, admin_user):
        shop_admin = admin.site._registry[Shop]
        request = rf.get("/admin/shopman/shop/")
        request.user = admin_user
        assert shop_admin.has_add_permission(request) is False

    def test_has_delete_permission_always_false(self, shop, rf, admin_user):
        shop_admin = admin.site._registry[Shop]
        request = rf.get("/admin/shopman/shop/")
        request.user = admin_user
        assert shop_admin.has_delete_permission(request) is False
        assert shop_admin.has_delete_permission(request, obj=shop) is False


# ── DayClosing readonly behavior ────────────────────────────────────


class TestDayClosingAdmin:
    def test_no_change_permission(self, db, rf, admin_user):
        closing_admin = admin.site._registry[DayClosing]
        request = rf.get("/admin/shopman/dayclosing/")
        request.user = admin_user
        assert closing_admin.has_change_permission(request) is False

    def test_no_delete_permission(self, db, rf, admin_user):
        closing_admin = admin.site._registry[DayClosing]
        request = rf.get("/admin/shopman/dayclosing/")
        request.user = admin_user
        assert closing_admin.has_delete_permission(request) is False


# ── OperatorAlert admin ─────────────────────────────────────────────


class TestOperatorAlertAdmin:
    def test_list_display_fields(self, db):
        alert_admin = admin.site._registry[OperatorAlert]
        assert "type" in alert_admin.list_display
        assert "severity" in alert_admin.list_display
        assert "acknowledged" in alert_admin.list_display

    def test_mark_acknowledged_action(self, db):
        alert_admin = admin.site._registry[OperatorAlert]
        action_names = [a.__name__ if callable(a) else a for a in alert_admin.actions]
        assert "mark_acknowledged" in action_names


# ── Order admin extensions ──────────────────────────────────────────


class TestOrderAdminExtensions:
    def test_order_has_fulfillment_inline(self, db):
        from shopman.orderman.models import Order

        from shopman.shop.admin.orders import FulfillmentOrderInline

        if Order not in admin.site._registry:
            pytest.skip("Order not registered in admin")

        order_admin_cls = type(admin.site._registry[Order])
        assert FulfillmentOrderInline in (order_admin_cls.inlines or [])

    def test_order_has_payment_info(self, db):
        from shopman.orderman.models import Order

        if Order not in admin.site._registry:
            pytest.skip("Order not registered in admin")

        order_admin_cls = type(admin.site._registry[Order])
        assert "payment_info" in (order_admin_cls.readonly_fields or ())


class TestProductAdminExtension:
    def test_product_has_allows_next_day_sale(self, db):
        from shopman.offerman.models import Product

        if Product not in admin.site._registry:
            pytest.skip("Product not registered in admin")

        product_admin_cls = type(admin.site._registry[Product])
        fieldsets = product_admin_cls.fieldsets or []
        for title, opts in fieldsets:
            if title == "Configuration":
                assert "allows_next_day_sale" in opts["fields"]
                return
        pytest.skip("Configuration fieldset not found")


class TestBatchAdminExtension:
    def test_batch_has_supplier_filter(self, db):
        from shopman.stockman.models import Batch

        from shopman.shop.admin.orders import SupplierFilter

        if Batch not in admin.site._registry:
            pytest.skip("Batch not registered in admin")

        batch_admin_cls = type(admin.site._registry[Batch])
        assert SupplierFilter in (batch_admin_cls.list_filter or [])

    def test_batch_has_expiry_filter(self, db):
        from shopman.stockman.models import Batch

        from shopman.shop.admin.orders import ExpiryStatusFilter

        if Batch not in admin.site._registry:
            pytest.skip("Batch not registered in admin")

        batch_admin_cls = type(admin.site._registry[Batch])
        assert ExpiryStatusFilter in (batch_admin_cls.list_filter or [])


# ── Dashboard callback ──────────────────────────────────────────────


class TestDashboardCallback:
    def test_returns_context_with_kpis(self, db):
        from shopman.backstage.admin.dashboard import dashboard_callback

        request = RequestFactory().get("/admin/")
        context = {}
        result = dashboard_callback(request, context)

        assert "order_summary" in result
        assert "revenue" in result
        assert "production" in result
        assert "kpi_stock_alerts" in result
        assert "chart_pedidos_status" in result
        assert "chart_vendas_7dias" in result
        assert "table_pedidos_pendentes" in result
        assert "recent_orders" in result
        assert "operator_alerts" in result

    def test_order_summary_structure(self, db):
        from shopman.backstage.admin.dashboard import dashboard_callback

        request = RequestFactory().get("/admin/")
        context = {}
        result = dashboard_callback(request, context)

        summary = result["order_summary"]
        assert hasattr(summary, "total")
        assert hasattr(summary, "new_count")
        assert hasattr(summary, "cards")

    def test_revenue_structure(self, db):
        from shopman.backstage.admin.dashboard import dashboard_callback

        request = RequestFactory().get("/admin/")
        context = {}
        result = dashboard_callback(request, context)

        revenue = result["revenue"]
        assert hasattr(revenue, "today_q")
        assert hasattr(revenue, "today_display")
        assert hasattr(revenue, "yesterday_q")
        assert hasattr(revenue, "trend_up")

    def test_format_brl(self):
        from shopman.backstage.projections.dashboard import _format_brl

        assert _format_brl(0) == "R$ 0,00"
        assert _format_brl(1500) == "R$ 15,00"
        assert _format_brl(150000) == "R$ 1.500,00"
        assert _format_brl(None) == "R$ 0,00"


class TestProductionBackstageRoutes:
    def test_operator_console_legacy_routes_do_not_exist(self, db):
        for route_name in (
            "backstage:production",
            "backstage:production_dashboard",
            "backstage:production_reports",
            "backstage:production_action",
            "backstage:production_void",
            "backstage:bulk_create_work_orders",
            "backstage:production_work_order_commitments",
        ):
            with pytest.raises(NoReverseMatch):
                reverse(route_name)

    def test_canonical_production_routes_are_admin_unfold(self, db):
        assert reverse("admin_console_production") == "/admin/operacao/producao/"
        assert reverse("admin_console_production_dashboard") == "/admin/operacao/producao/painel/"
        assert reverse("admin_console_production_reports") == "/admin/operacao/producao/relatorios/"
        assert reverse("admin_console_production_bulk_create") == "/admin/operacao/producao/criar/"
