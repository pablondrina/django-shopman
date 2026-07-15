"""Regression: the D-1 clearance discount must survive the persisted Session
pipeline (add_line op → normalize → modifiers), not only direct modifier calls.

Root cause of the historical dormancy: ``Session._normalize_items`` whitelists
``line_id/sku/name/qty/unit_price_q/line_total_q/meta`` and drops a top-level
``is_d1``, so by the time ``AvailabilityDiscountModifier`` ran the flag was gone
and nothing wrote ``session.data["availability"]``. The fix persists the flag in
the durable line ``meta`` (via ``ModifyService._op_add_line``) and teaches the
modifier to read it there. These tests drive the REAL ``modify_session`` path so
the whitelist strip can never silence the discount again.
"""
from __future__ import annotations

import pytest
from shopman.orderman.models import Session

from shopman.shop.models import Channel, RuleConfig
from shopman.shop.services import sessions as session_service

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _web_channel():
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})


@pytest.fixture
def d1_rule():
    RuleConfig.objects.create(
        ref="d1_discount",
        rule_path="shopman.shop.rules.pricing.D1Rule",
        label="Desconto D-1 (sobras)",
        params={"discount_percent": 50},
        enabled=True,
        priority=15,
    )
    from shopman.shop.rules import engine
    try:
        engine.get_active_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass


def _add_d1_line(session: Session, *, is_d1: bool) -> Session:
    op = {"op": "add_line", "sku": "NOSUCH", "qty": 1, "unit_price_q": 1000}
    if is_d1:
        op["is_d1"] = True
    return session_service.modify_session(
        session_key=session.session_key, channel_ref="web", ops=[op]
    )


def test_op_is_d1_lands_in_line_meta():
    """A top-level op ``is_d1`` is persisted into the durable line ``meta``."""
    session = session_service.create_session("web", data={})
    session = _add_d1_line(session, is_d1=True)
    line = session.items[0]
    assert line["meta"].get("is_d1") is True
    assert "is_d1" not in line  # never as a stripped top-level field


def test_d1_discount_applies_through_modify_session(d1_rule):
    session = session_service.create_session("web", data={})
    session = _add_d1_line(session, is_d1=True)
    assert session.items[0]["unit_price_q"] == 500  # 1000 − 50%
    assert session.pricing.get("d1_discount", {}).get("total_discount_q") == 500


def test_non_d1_line_keeps_full_price(d1_rule):
    session = session_service.create_session("web", data={})
    session = _add_d1_line(session, is_d1=False)
    assert session.items[0]["unit_price_q"] == 1000
    assert "d1_discount" not in (session.pricing or {})
