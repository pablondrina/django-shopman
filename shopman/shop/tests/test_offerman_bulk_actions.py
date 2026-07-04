"""Bulk actions do admin de Product disparam product_updated (re-projeção externa).

Regressão: publish/unpublish/pause/resume usavam queryset.update() → pulavam
Product.save() → product_updated nunca disparava → o iFood (e outros canais
projetados) NÃO retraía o produto despublicado em massa. Roda no framework porque
o admin de Product depende de django.contrib.admin/import_export.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from shopman.offerman.contrib.admin_unfold.admin import ProductAdmin
from shopman.offerman.models import Product
from shopman.offerman.signals import product_updated

pytestmark = pytest.mark.django_db


class _Req:
    pass


@pytest.fixture
def product_admin():
    a = ProductAdmin(Product, AdminSite())
    a.message_user = lambda *args, **kwargs: None
    return a


def _capture():
    seen = []

    def receiver(sender, sku, **kwargs):
        seen.append(sku)

    product_updated.connect(receiver, weak=False)
    return seen, receiver


def test_unpublish_bulk_fires_product_updated(product_admin):
    p1 = Product.objects.create(sku="BULKAA", name="A", unit="un", base_price_q=100, is_published=True)
    p2 = Product.objects.create(sku="BULKBB", name="B", unit="un", base_price_q=100, is_published=True)
    seen, receiver = _capture()
    try:
        product_admin.unpublish_products(_Req(), Product.objects.filter(pk__in=[p1.pk, p2.pk]))
    finally:
        product_updated.disconnect(receiver)

    p1.refresh_from_db()
    assert p1.is_published is False
    assert set(seen) == {"BULKAA", "BULKBB"}


def test_pause_bulk_skips_noop(product_admin):
    p1 = Product.objects.create(sku="BULKCC", name="C", unit="un", base_price_q=100, is_sellable=True)
    p2 = Product.objects.create(sku="BULKDD", name="D", unit="un", base_price_q=100, is_sellable=False)
    seen, receiver = _capture()
    try:
        product_admin.pause_products(_Req(), Product.objects.filter(pk__in=[p1.pk, p2.pk]))
    finally:
        product_updated.disconnect(receiver)

    assert seen == ["BULKCC"]  # p2 já era não-vendável → sem re-projeção
