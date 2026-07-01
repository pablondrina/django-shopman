"""Showcase (Expositor) — model + admin form/links."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import site
from shopman.offerman.models import Collection

from shopman.shop.admin.showcase import ShowcaseAdmin, ShowcaseForm
from shopman.shop.models import Showcase


@pytest.fixture
def collections(db):
    Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=1)
    Collection.objects.create(ref="doces", name="Doces", is_active=True, sort_order=2)


def test_model_basics(db):
    sc = Showcase.objects.create(ref="tv", name="TV", kind="menuboard", collections=["paes", " doces ", ""])
    assert str(sc) == "TV"
    assert sc.collection_refs() == ["paes", "doces"]  # limpa vazios/espaços
    assert sc.is_feed is False
    assert Showcase.objects.create(ref="g", name="G", kind="google").is_feed is True


def test_form_multiselect_saves_collection_refs(collections):
    form = ShowcaseForm(data={"ref": "cafe", "name": "Café", "kind": "menuboard", "collections": ["paes", "doces"]})
    assert form.is_valid(), form.errors
    sc = form.save()
    assert sc.collections == ["paes", "doces"]


def test_form_rejects_unknown_collection(collections):
    form = ShowcaseForm(data={"ref": "x", "name": "X", "kind": "menuboard", "collections": ["fantasma"]})
    assert not form.is_valid()
    assert "collections" in form.errors


def test_form_reopens_with_selection(collections):
    sc = Showcase.objects.create(ref="cafe", name="Café", kind="menuboard", collections=["paes"])
    assert ShowcaseForm(instance=sc).fields["collections"].initial == ["paes"]


def test_admin_surface_links(db):
    admin = ShowcaseAdmin(Showcase, site)
    mb = Showcase.objects.create(ref="tv", name="TV", kind="menuboard")
    assert "/menuboard/tv/" in admin.surface_links(mb)
    g = Showcase.objects.create(ref="google", name="G", kind="google")
    assert "/feed/google.xml" in admin.surface_links(g) and "platform=meta" not in admin.surface_links(g)
    m = Showcase.objects.create(ref="meta", name="M", kind="meta")
    assert "platform=meta" in admin.surface_links(m)
