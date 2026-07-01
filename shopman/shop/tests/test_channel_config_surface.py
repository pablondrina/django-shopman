"""
ChannelConfig — aspectos de SUPERFÍCIE (capability + content).

Generalizam o canal para o primitivo Superfície: capacidade (transacional/
display/feed) e fonte de conteúdo (ListingItems explícitos ou uma Collection).
Zero migração no Core — vivem em Channel.config (JSON), como os demais aspectos.
"""

from __future__ import annotations

import pytest

from shopman.shop.config import ChannelConfig


def test_defaults_are_transactional_listing():
    """Canais existentes, sem override, permanecem transacionais com fonte listing."""
    c = ChannelConfig()
    assert c.capability == "transactional"
    assert c.content.source == "listing"
    assert c.content.collection is None
    c.validate()  # não levanta


def test_defaults_dict_carries_surface_aspects():
    d = ChannelConfig.defaults()
    assert d["capability"] == "transactional"
    assert d["content"] == {"source": "listing", "collection": None}


def test_from_dict_display_surface_fed_by_collection():
    c = ChannelConfig.from_dict(
        {"capability": "display", "content": {"source": "collection", "collection": "cafe-da-manha"}}
    )
    assert c.capability == "display"
    assert c.content.source == "collection"
    assert c.content.collection == "cafe-da-manha"
    c.validate()


def test_from_dict_ignores_unknown_content_keys():
    """_safe_init filtra chaves desconhecidas do content."""
    c = ChannelConfig.from_dict({"content": {"source": "listing", "bogus": 1}})
    assert c.content.source == "listing"


@pytest.mark.parametrize("bad", ["sales", "displays", "", "TRANSACTIONAL"])
def test_invalid_capability_raises(bad):
    c = ChannelConfig.from_dict({"capability": bad})
    with pytest.raises(ValueError, match="capability"):
        c.validate()


def test_invalid_content_source_raises():
    c = ChannelConfig.from_dict({"content": {"source": "rule"}})
    with pytest.raises(ValueError, match="content.source"):
        c.validate()


def test_collection_source_requires_collection_ref():
    c = ChannelConfig.from_dict({"content": {"source": "collection"}})
    with pytest.raises(ValueError, match="content.collection"):
        c.validate()

    blank = ChannelConfig.from_dict({"content": {"source": "collection", "collection": "  "}})
    with pytest.raises(ValueError, match="content.collection"):
        blank.validate()


def test_to_dict_round_trips_surface_aspects():
    original = ChannelConfig.from_dict(
        {"capability": "feed", "content": {"source": "collection", "collection": "vendaveis-online"}}
    )
    restored = ChannelConfig.from_dict(original.to_dict())
    assert restored.capability == "feed"
    assert restored.content.source == "collection"
    assert restored.content.collection == "vendaveis-online"


def test_cascade_channel_override_wins():
    """deep_merge: override de capability no nível canal vence o default da loja."""
    from shopman.shop.config import deep_merge

    base = ChannelConfig.defaults()  # transactional
    merged = deep_merge(base, {"capability": "display", "content": {"source": "collection", "collection": "tv-1"}})
    c = ChannelConfig.from_dict(merged)
    assert c.capability == "display"
    assert c.content.collection == "tv-1"
