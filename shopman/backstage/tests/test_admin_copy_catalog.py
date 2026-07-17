"""Catálogo de copy — página Admin canônica (navegação chave↔tela)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from shopman.backstage.projections.copy_catalog import build_copy_catalog


@pytest.fixture()
def staff_client(client, db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
    user = get_user_model().objects.create_superuser("copyadmin", "c@example.com", "pw")
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_projection_groups_keys_by_surface_and_screen():
    catalog = build_copy_catalog()

    assert catalog.total_keys >= 300
    assert catalog.mapped_keys >= 300
    labels = {(group.surface, group.screen) for group in catalog.groups}
    assert ("Loja", "Página do produto") in labels
    pdp = next(g for g in catalog.groups if g.screen == "Página do produto")
    assert "PRODUCT_CROSS_SELL_HEADING" in [row.key for row in pdp.rows]


@pytest.mark.django_db
def test_projection_search_finds_key_by_visible_text():
    # O operador procura pelo TEXTO que viu na tela, não pela chave.
    catalog = build_copy_catalog(q="Você também pode gostar")

    rows = [row.key for group in catalog.groups for row in group.rows]
    assert rows == ["PRODUCT_CROSS_SELL_HEADING"]


@pytest.mark.django_db
def test_projection_counts_active_overrides():
    from shopman.shop.models import OmotenashiCopy

    OmotenashiCopy.objects.create(
        key="PRODUCT_CROSS_SELL_HEADING", moment="*", audience="*",
        title="Combina com", active=True,
    )
    catalog = build_copy_catalog(q="PRODUCT_CROSS_SELL_HEADING")
    row = next(row for group in catalog.groups for row in group.rows)
    assert row.override_count == 1
    assert catalog.active_overrides == 1


@pytest.mark.django_db
def test_catalog_page_renders_grouped_by_screen(staff_client):
    resp = staff_client.get(reverse("admin_console_copy_catalog"))

    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Catálogo de copy" in content
    assert "Página do produto" in content
    assert "PRODUCT_CROSS_SELL_HEADING" in content
    # Link de personalizar já leva com a chave preenchida.
    assert "/admin/shop/omotenashicopy/add/?key=PRODUCT_CROSS_SELL_HEADING" in content


@pytest.mark.django_db
def test_catalog_page_filters_by_query(staff_client):
    resp = staff_client.get(
        reverse("admin_console_copy_catalog"), {"q": "Você também pode gostar"}
    )

    content = resp.content.decode()
    assert "PRODUCT_CROSS_SELL_HEADING" in content
    assert "TRACKING_STEP_RECEIVED" not in content


@pytest.mark.django_db
def test_catalog_requires_view_permission(client, db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
    user = get_user_model().objects.create_user("semperm", password="x", is_staff=True)
    client.force_login(user)

    resp = client.get(reverse("admin_console_copy_catalog"))

    assert resp.status_code in (302, 403)


@pytest.mark.django_db
def test_sidebar_points_copy_omotenashi_to_catalog(staff_client):
    from django.contrib import admin as dj_admin
    from django.test import RequestFactory

    request = RequestFactory().get("/admin/")
    request.user = get_user_model().objects.get(username="copyadmin")
    groups = dj_admin.site.get_sidebar_list(request)
    config = next(group for group in groups if group["title"] == "Configurações")
    item = next(i for i in config["items"] if i["title"] == "Copy Omotenashi")
    assert str(item["link"]).endswith("/admin/configuracao/copy/")
