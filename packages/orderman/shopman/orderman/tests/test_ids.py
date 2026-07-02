import re
from datetime import date

import pytest
from shopman.orderman.contrib.refs.types import ORDER_REF
from shopman.orderman.ids import generate_order_ref
from shopman.refs.registry import get_ref_type, register_ref_type

# generate_order_ref sorteia e checa colisão no banco (retry) → precisa de DB.
pytestmark = pytest.mark.django_db


def test_generate_order_ref_uses_yymmdd_business_date():
    if get_ref_type("ORDER_REF") is None:
        register_ref_type(ORDER_REF)

    ref = generate_order_ref(channel_ref="pdv", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"PDV-260504-[A-Z]\d{2}", ref)


def test_generate_order_ref_accepts_real_channel_refs():
    if get_ref_type("ORDER_REF") is None:
        register_ref_type(ORDER_REF)

    ref = generate_order_ref(channel_ref="delivery", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"DELIVERY-260504-[A-Z]\d{2}", ref)


def test_generate_order_ref_fallback_keeps_channel_and_yymmdd(monkeypatch):
    def unavailable(*args, **kwargs):
        raise LookupError

    monkeypatch.setattr("shopman.refs.generators.generate_value", unavailable)
    ref = generate_order_ref(channel_ref="web", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"WEB-260504-[A-Z]\d{2}", ref)


def test_generate_order_ref_retries_past_collision(monkeypatch):
    # Aleatório pode repetir: se o candidato já existe, sorteia de novo até um livre.
    from shopman.orderman.models import Order

    if get_ref_type("ORDER_REF") is None:
        register_ref_type(ORDER_REF)
    Order.objects.create(ref="WEB-260504-A17", channel_ref="WEB", session_key="k1", total_q=0)

    seq = iter(["WEB-260504-A17", "WEB-260504-B22"])  # 1º colide, 2º livre
    monkeypatch.setattr("shopman.orderman.ids._order_ref_candidate", lambda ch, day: next(seq))

    ref = generate_order_ref(channel_ref="web", business_date=date(2026, 5, 4))
    assert ref == "WEB-260504-B22"
