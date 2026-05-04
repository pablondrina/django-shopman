import re
from datetime import date

from shopman.orderman.contrib.refs.types import ORDER_REF
from shopman.orderman.ids import generate_order_ref
from shopman.refs.registry import get_ref_type, register_ref_type


def test_generate_order_ref_uses_yymmdd_business_date():
    if get_ref_type("ORDER_REF") is None:
        register_ref_type(ORDER_REF)

    ref = generate_order_ref(channel_ref="pdv", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"PDV-260504-[A-Z0-9]{8}", ref)


def test_generate_order_ref_accepts_real_channel_refs():
    if get_ref_type("ORDER_REF") is None:
        register_ref_type(ORDER_REF)

    ref = generate_order_ref(channel_ref="delivery", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"DELIVERY-260504-[A-Z0-9]{8}", ref)


def test_generate_order_ref_fallback_keeps_channel_and_yymmdd(monkeypatch):
    def unavailable(*args, **kwargs):
        raise LookupError

    monkeypatch.setattr("shopman.refs.generators.generate_value", unavailable)
    ref = generate_order_ref(channel_ref="web", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"WEB-260504-[A-Z0-9]{8}", ref)
