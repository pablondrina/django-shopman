"""Channel admin — capability + content (primitivo Superfície) no ChannelForm."""

from __future__ import annotations

import pytest

from shopman.shop.admin.channel import ChannelForm


@pytest.mark.django_db
def test_form_defaults_to_transactional_listing():
    form = ChannelForm(data={"ref": "web", "name": "Web", "display_order": 0})
    assert form.is_valid(), form.errors
    ch = form.save()
    assert ch.config["capability"] == "transactional"
    assert ch.config["content"] == {"source": "listing"}


@pytest.mark.django_db
def test_form_saves_display_surface_fed_by_collection():
    form = ChannelForm(
        data={
            "ref": "menuboard",
            "name": "Menuboard",
            "display_order": 0,
            "capability": "display",
            "content_source": "collection",
            "content_collection": "cafe-da-manha",
        }
    )
    assert form.is_valid(), form.errors
    ch = form.save()
    assert ch.config["capability"] == "display"
    assert ch.config["content"] == {"source": "collection", "collection": "cafe-da-manha"}


@pytest.mark.django_db
def test_form_rejects_collection_source_without_ref():
    form = ChannelForm(
        data={
            "ref": "bad",
            "name": "Bad",
            "display_order": 0,
            "content_source": "collection",
            "content_collection": "",
        }
    )
    assert not form.is_valid()  # ChannelConfig.validate exige a coleção


@pytest.mark.django_db
def test_form_roundtrips_from_instance():
    form = ChannelForm(
        data={
            "ref": "ifood",
            "name": "iFood",
            "display_order": 0,
            "capability": "feed",
            "content_source": "listing",
        }
    )
    assert form.is_valid(), form.errors
    ch = form.save()
    # reabrir o form no instance mostra os valores salvos
    reopened = ChannelForm(instance=ch)
    assert reopened.fields["capability"].initial == "feed"
    assert reopened.fields["content_source"].initial == "listing"
