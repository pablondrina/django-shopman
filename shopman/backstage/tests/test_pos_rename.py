"""POS comanda rename (set-handle) semantics."""

from __future__ import annotations

import pytest
from shopman.orderman.models import Session

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError


@pytest.fixture
def pos_env(db):
    Shop.objects.create(name="Test Shop", brand_name="Test")
    Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
    POSTab.objects.create(ref="00003001", label="3001")


def _open_tab(tab_ref: str) -> Session:
    opened = build_open_tab(pos_service.open_pos_tab(
        channel_ref="pdv", tab_ref=tab_ref,
        actor="pos:alice", operator_username="alice",
    ))
    return Session.objects.get(session_key=opened["tab_session_key"])


@pytest.mark.django_db
def test_rename_updates_handle_and_markers(pos_env):
    session = _open_tab("3001")

    result = pos_service.rename_pos_tab(
        channel_ref="pdv", session_key=session.session_key,
        new_tab_ref="João Mesa", actor="pos:alice", operator_username="alice",
    )

    session.refresh_from_db()
    assert session.handle_ref == "JOÃO MESA"
    assert session.data["tab_ref"] == "JOÃO MESA"
    assert session.data["tab_display"] == "João Mesa"
    assert build_open_tab(result)["tab_ref"] == "JOÃO MESA"
    assert build_open_tab(result)["tab_display"] == "João Mesa"


@pytest.mark.django_db
def test_rename_to_handle_in_use_is_rejected(pos_env):
    first = _open_tab("3001")
    POSTab.objects.create(ref="00003002", label="3002")
    second = _open_tab("3002")

    with pytest.raises(PosIntentError) as exc:
        pos_service.rename_pos_tab(
            channel_ref="pdv", session_key=second.session_key,
            new_tab_ref="3001", actor="pos:alice", operator_username="alice",
        )
    assert exc.value.code == "tab_in_use"
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.state == "open"
    assert second.data.get("tab_ref") == "00003002"


@pytest.mark.django_db
def test_rename_rejects_disallowed_chars(pos_env):
    session = _open_tab("3001")

    with pytest.raises(PosIntentError) as exc:
        pos_service.rename_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            new_tab_ref="Mesa/5", actor="pos:alice", operator_username="alice",
        )
    assert exc.value.code == "invalid_tab_ref"


@pytest.mark.django_db
def test_rename_to_same_ref_is_noop(pos_env):
    session = _open_tab("3001")

    result = pos_service.rename_pos_tab(
        channel_ref="pdv", session_key=session.session_key,
        new_tab_ref="3001", actor="pos:alice", operator_username="alice",
    )
    assert build_open_tab(result)["tab_ref"] == "00003001"
