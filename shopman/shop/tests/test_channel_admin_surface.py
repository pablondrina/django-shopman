"""Channel admin — capability + coleção-fonte (primitivo Superfície) no ChannelForm.

Fluxo refinado: capacidade + coleção (dropdown das Collections ativas); ``source`` é
inferido (coleção → collection); Menuboard/Feed exigem coleção; links prontos no admin.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import Collection

from shopman.shop.admin.channel import ChannelForm
from shopman.shop.models import Channel


@pytest.fixture
def cafe(db):
    return Collection.objects.create(ref="cafe-da-manha", name="Café da Manhã", is_active=True)


@pytest.mark.django_db
def test_form_defaults_to_transactional_listing():
    form = ChannelForm(data={"ref": "web", "name": "Web", "display_order": 0})
    assert form.is_valid(), form.errors
    ch = form.save()
    assert ch.config["capability"] == "transactional"
    assert ch.config["content"] == {"source": "listing"}


@pytest.mark.django_db
def test_display_surface_fed_by_collection(cafe):
    form = ChannelForm(
        data={
            "ref": "menuboard", "name": "Menuboard", "display_order": 0,
            "capability": "display", "content_collection": "cafe-da-manha",
        }
    )
    assert form.is_valid(), form.errors
    ch = form.save()
    assert ch.config["capability"] == "display"
    assert ch.config["content"] == {"source": "collection", "collection": "cafe-da-manha"}


@pytest.mark.django_db
def test_source_is_inferred_from_collection(cafe):
    # coleção presente → source=collection sem o operador escolher explicitamente
    form = ChannelForm(data={"ref": "web", "name": "Web", "display_order": 0, "content_collection": "cafe-da-manha"})
    assert form.is_valid(), form.errors
    assert form.save().config["content"] == {"source": "collection", "collection": "cafe-da-manha"}


@pytest.mark.django_db
def test_display_requires_collection(db):
    form = ChannelForm(data={"ref": "tv", "name": "TV", "display_order": 0, "capability": "display"})
    assert not form.is_valid()
    assert "content_collection" in form.errors


@pytest.mark.django_db
def test_feed_requires_collection(db):
    form = ChannelForm(data={"ref": "g", "name": "Google", "display_order": 0, "capability": "feed"})
    assert not form.is_valid()
    assert "content_collection" in form.errors


@pytest.mark.django_db
def test_rejects_unknown_collection(db):
    # ChoiceField: coleção inexistente não é opção válida
    form = ChannelForm(
        data={"ref": "tv", "name": "TV", "display_order": 0, "capability": "display", "content_collection": "fantasma"}
    )
    assert not form.is_valid()
    assert "content_collection" in form.errors


@pytest.mark.django_db
def test_surface_links_render(cafe):
    from django.contrib.admin.sites import site

    from shopman.shop.admin.channel import ChannelAdmin

    ch = Channel.objects.create(ref="menuboard", name="MB", config={"capability": "display", "content": {"source": "collection", "collection": "cafe-da-manha"}})
    admin = ChannelAdmin(Channel, site)
    assert "/menuboard/menuboard/" in admin.surface_links(ch)

    feed = Channel.objects.create(ref="google", name="G", config={"capability": "feed", "content": {"source": "collection", "collection": "cafe-da-manha"}})
    links = admin.surface_links(feed)
    assert "/feed/google.xml" in links and "platform=meta" in links
