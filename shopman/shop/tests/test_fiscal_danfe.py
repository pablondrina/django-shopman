"""DANFE NFC-e — projeção + view de operador (o 'lampejo' do cupom fiscal)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Shop
from shopman.shop.views.fiscal_danfe import build_danfe


@pytest.fixture
def emitted_order(db):
    Shop.objects.create(name="Nelson", brand_name="Nelson Boulangerie", legal_name="NHK Ltda")
    order = Order.objects.create(
        ref="WEB-1", channel_ref="web", session_key="k1", status="completed", total_q=1800,
        data={
            "customer": {"name": "Ana"},
            "payment": {"method": "pix"},
            "fiscal": {"issue_document": True},
            "nfce_access_key": "41260799999999000191650010000012342876543210",
            "nfce_number": 1234, "nfce_series": "1", "nfce_protocol": "141260000012345",
            "nfce_status": "autorizado",
            "nfce_danfe_url": "https://homologacao.focusnfe.com.br/danfe.pdf",
            "nfce_qrcode_url": "http://www.fazenda.pr.gov.br/nfce/qrcode?p=41260799999999000191",
        },
    )
    OrderItem.objects.create(
        order=order, line_id="L1", sku="PAO", name="Pão", qty="2", unit_price_q=500, line_total_q=1000
    )
    OrderItem.objects.create(
        order=order, line_id="L2", sku="BOLO", name="Bolo", qty="1", unit_price_q=800, line_total_q=800
    )
    return order


def test_build_danfe_emitted(emitted_order):
    d = build_danfe("WEB-1")
    assert d is not None
    assert d.emitted is True
    assert d.is_homolog is True
    assert d.environment_label == "Homologação"
    assert d.item_count == 2
    assert d.total_display == "R$ 18,00"
    assert d.payment_label == "PIX"
    assert d.customer_name == "Ana"
    # chave agrupada de 4 em 4
    assert d.chave_grouped.startswith("4126 0799")
    # QR gerado inline
    assert d.qr_svg.startswith("<?xml") or "<svg" in d.qr_svg


def test_build_danfe_missing_order(db):
    assert build_danfe("NOPE") is None


def test_build_danfe_not_emitted(db):
    Shop.objects.create(name="Nelson")
    Order.objects.create(ref="WEB-2", channel_ref="web", session_key="k2", status="completed", total_q=500)
    d = build_danfe("WEB-2")
    assert d is not None
    assert d.emitted is False
    assert d.status == "não emitida"
    assert d.qr_svg == ""


def test_view_requires_staff(client, emitted_order):
    user = User.objects.create_user("plain", password="pw", is_staff=False)
    client.force_login(user)
    assert client.get("/fiscal/danfe/WEB-1/").status_code in (302, 404)


def test_view_renders_for_staff(client, emitted_order):
    staff = User.objects.create_user("op", password="pw", is_staff=True)
    client.force_login(staff)
    resp = client.get("/fiscal/danfe/WEB-1/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "SEM VALOR FISCAL" in body  # carimbo obrigatório de homologação
    assert "DANFE NFC-e" in body
    assert "<svg" in body  # QR inline


def test_view_404_unknown_order(client, db):
    staff = User.objects.create_user("op2", password="pw", is_staff=True)
    client.force_login(staff)
    assert client.get("/fiscal/danfe/GHOST/").status_code == 404
