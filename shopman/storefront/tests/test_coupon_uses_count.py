"""``Coupon.max_uses`` deixa de ser decorativo: o commit conta o uso.

Regressão do audit pré-go-live: ``uses_count`` nunca era incrementado em nenhum
código — um cupom "primeiros 10 clientes" funcionava para sempre. O uso é
contado no ``_on_commit`` do lifecycle (uma vez por pedido, só quando o cupom
efetivamente descontou), atômico via ``F()``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import Channel, Shop
from shopman.shop.services import sessions
from shopman.storefront.models import Coupon, Promotion

pytestmark = pytest.mark.django_db


@pytest.fixture
def coupon(db):
    Shop.objects.create(name="Test Shop")
    Product.objects.create(sku="PAO-TESTE", name="Pão", base_price_q=2500)
    Channel.objects.create(ref="web", name="Web")
    now = timezone.now()
    promo = Promotion.objects.create(
        name="Boas-vindas",
        type=Promotion.FIXED,
        value=500,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    return Coupon.objects.create(code="BEMVINDO", promotion=promo, max_uses=10)


def _commit(coupon_code: str | None, django_capture_on_commit_callbacks):
    session = sessions.create_session("web")
    ops = [
        {"op": "add_line", "sku": "PAO-TESTE", "name": "Pão", "qty": 1, "unit_price_q": 2500},
        {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001"}},
        {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
    ]
    if coupon_code:
        ops.append({"op": "set_data", "path": "coupon_code", "value": coupon_code})
    sessions.modify_session(session_key=session.session_key, channel_ref="web", ops=ops)
    with django_capture_on_commit_callbacks(execute=True):
        sessions.commit_session(
            session_key=session.session_key,
            channel_ref="web",
            idempotency_key=sessions.new_idempotency_key(),
        )


def test_commit_with_coupon_increments_uses_count(coupon, django_capture_on_commit_callbacks):
    _commit("BEMVINDO", django_capture_on_commit_callbacks)
    coupon.refresh_from_db()
    assert coupon.uses_count == 1


def test_commit_without_coupon_does_not_count(coupon, django_capture_on_commit_callbacks):
    _commit(None, django_capture_on_commit_callbacks)
    coupon.refresh_from_db()
    assert coupon.uses_count == 0


def test_exhausted_coupon_stops_discounting(coupon, django_capture_on_commit_callbacks):
    coupon.uses_count = coupon.max_uses
    coupon.save(update_fields=["uses_count"])

    _commit("BEMVINDO", django_capture_on_commit_callbacks)
    coupon.refresh_from_db()
    # Esgotado: não desconta e não conta de novo.
    assert coupon.uses_count == coupon.max_uses
