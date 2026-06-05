"""Home projection contract guardrails."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_home_projection_keeps_operational_status_single_sourced(rf):
    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home

    shop = Shop.load() or Shop.objects.create(name="Test Padaria")
    shop.opening_hours = {
        day: {"open": "07:00", "close": "19:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    }
    shop.save()
    from django.core.cache import cache as django_cache

    from shopman.shop.models.shop import SHOP_CACHE_KEY

    django_cache.delete(SHOP_CACHE_KEY)

    payload = projection_data(build_home(rf.get("/api/v1/storefront/home/")))

    assert {"is_open", "opens_at", "closes_at"}.isdisjoint(payload["omotenashi"])
    assert set(payload["shop_status"]) == {"is_open", "label", "message", "opens_at", "closes_at"}
    assert "notices" in payload
    assert all({"ref", "tone", "title", "message", "priority", "actions"} <= set(notice) for notice in payload["notices"])
    assert payload["shop_status"]["is_open"] in {True, False}
    assert payload["shop_status"]["label"] in {"Aberto agora", "Fechado agora"}


def test_home_projection_promotes_whatsapp_origin_as_contract_notice(rf):
    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home

    Shop.load() or Shop.objects.create(name="Test Padaria")

    request = rf.get("/api/v1/storefront/home/")
    request.session = {"origin_channel": "whatsapp"}

    payload = projection_data(build_home(request))
    notices = {notice["ref"]: notice for notice in payload["notices"]}

    assert notices["origin_whatsapp"]["priority"] == "contextual"
    assert notices["origin_whatsapp"]["tone"] == "info"
    assert notices["origin_whatsapp"]["actions"][0]["href"] == "/checkout"
