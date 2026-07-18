"""Integration: the social PIM tab composes with Offerman's Product admin.

Runs under the full deployment stack (config.settings_test) so admin_unfold +
fiscalman + the social contrib are all registered and stacked on ProductAdmin.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from shopman.offerman.contrib.social.schema import get_social_attributes
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


def _flatten(fieldsets) -> list[str]:
    return [str(label) for label, _ in fieldsets]


def _fields_of(fieldsets, label):
    for lbl, opts in fieldsets:
        if str(lbl) == label:
            return list(opts.get("fields", ()))
    return []


class TestSocialTabComposition:
    def setup_method(self):
        self.model_admin = admin.site._registry[Product]
        self.request = RequestFactory().get("/admin/offerman/product/1/change/")
        self.request.user = User(is_superuser=True, is_staff=True)

    def test_social_tab_present(self):
        labels = _flatten(self.model_admin.get_fieldsets(self.request))
        assert "Redes sociais" in labels

    def test_fiscal_tab_still_present(self):
        # Composition: the social contrib stacked on top of fiscalman, not over it.
        labels = _flatten(self.model_admin.get_fieldsets(self.request))
        assert "Fiscal (NFC-e)" in labels

    def test_social_fieldset_fields(self):
        fields = _fields_of(self.model_admin.get_fieldsets(self.request), "Redes sociais")
        for expected in (
            "social_brand", "social_gtin", "social_condition",
            "social_google_category", "social_hashtags", "social_caption",
        ):
            assert expected in fields

    def test_social_tab_is_unfold_tab(self):
        fieldsets = self.model_admin.get_fieldsets(self.request)
        social = next(opts for lbl, opts in fieldsets if str(lbl) == "Redes sociais")
        assert "tab" in social.get("classes", ())


class TestSocialFormPersistence:
    def _form_class(self):
        model_admin = admin.site._registry[Product]
        request = RequestFactory().get("/admin/offerman/product/add/")
        request.user = User(is_superuser=True, is_staff=True)
        return model_admin.get_form(request)

    def test_valid_social_fields_write_metadata(self, db):
        product = Product.objects.create(sku="SOCIAL-1", name="Baguete", base_price_q=900)
        Form = self._form_class()
        form = Form(
            data={
                "sku": product.sku, "name": product.name, "unit": product.unit,
                "base_price_q": product.base_price_q,
                "availability_policy": product.availability_policy,
                "is_published": "on", "is_sellable": "on",
                "social_brand": "Nelson",
                "social_gtin": "4006381333931",
                "social_condition": "new",
                "social_google_category": "2271",
                "social_hashtags": "#pão artesanal",
                "social_caption": "Fresquinho.",
            },
            instance=product,
        )
        assert form.is_valid(), form.errors
        saved = form.save()
        attrs = get_social_attributes(saved)
        assert attrs.brand == "Nelson"
        assert attrs.gtin == "4006381333931"
        assert attrs.google_product_category == "2271"
        assert attrs.hashtags == ["pão", "artesanal"]
        assert saved.metadata["social"]["brand"] == "Nelson"

    def test_invalid_gtin_rejected(self, db):
        product = Product.objects.create(sku="SOCIAL-2", name="Pão", base_price_q=500)
        Form = self._form_class()
        form = Form(
            data={
                "sku": product.sku, "name": product.name, "unit": product.unit,
                "base_price_q": product.base_price_q,
                "availability_policy": product.availability_policy,
                "is_published": "on", "is_sellable": "on",
                "social_gtin": "123",  # invalid length/checksum
            },
            instance=product,
        )
        assert not form.is_valid()
        assert any("GTIN" in str(e) for e in form.errors.get("__all__", []))
