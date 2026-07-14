"""WP-A (AVAILABILITY-SALE-PRODUCTION-PLAN §3): reprodução do commit falho do QA.

Fluxo do QA staging (2026-07-14): cliente adiciona item SEM estoque pronto mas
com fornada planejada para HOJE (holds planejados, ``expires_at=None``), faz
login via access link, faz checkout com data de HOJE e envia. O envio falhou:

    stock.hold: create_hold failed sku=BAGUETE qty=2.000 code=INSUFFICIENT_AVAILABLE
    → "BAGUETE ficou indisponível antes de concluirmos a sua reserva."

Estes testes fixam a invariante: o pedido ADOTA os holds da sacola (os mesmos
hold ids, sem ``create_hold`` novo) através de TODOS os caminhos de login.
Instrumentação: cada teste afirma sobre os hold ids concretos, então uma
adoção zerada (fallback ``create_hold``) falha o assert mesmo quando o commit
"dá certo" por sorte de capacidade.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from shopman.doorman.models import AccessLink
from shopman.guestman.models import Customer
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order
from shopman.stockman.models import Hold, Position, PositionKind
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.services.planning import StockPlanning

from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ── seed ──────────────────────────────────────────────────────────────────────


def _seed_planned_bakery(*, planned_qty: int = 2) -> Product:
    """Vitrine com BAGUETE sem estoque pronto e fornada planejada para HOJE.

    ``planned_qty`` default 2 = exatamente a qty do pedido: qualquer hold
    fantasma (ou dupla reserva) estoura a capacidade, como no QA.
    """
    Shop.objects.create(
        name="Demo Bakery",
        brand_name="Demo Bakery",
        short_name="Demo",
        phone="554333231997",
    )
    Channel.objects.create(ref="web", name="Loja Online")
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    product = Product.objects.create(
        sku=SKU,
        name="Baguete",
        base_price_q=1200,
        is_published=True,
        is_sellable=True,
    )
    ListingItem.objects.create(
        listing=listing,
        product=product,
        price_q=1200,
        is_published=True,
        is_sellable=True,
    )
    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    StockPlanning.plan(
        Decimal(str(planned_qty)),
        product,
        timezone.localdate(),
        position=position,
        reason="fornada planejada (teste WP-A)",
    )
    return product


def _customer() -> Customer:
    return Customer.objects.create(
        ref="CUST-QA",
        first_name="Pablo",
        last_name="QA",
        phone="5543999990001",
    )


# ── helpers de fluxo ─────────────────────────────────────────────────────────


def _add_to_cart(client: Client, qty: int = 2) -> str:
    resp = client.put(
        f"/api/v1/cart/skus/{SKU}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    cart_key = client.session.get("cart_session_key")
    assert cart_key, "add deveria ter criado a sessão de sacola"
    return cart_key


def _active_hold_ids(reference: str) -> list[str]:
    return [
        h.hold_id
        for h in Hold.objects.filter(metadata__reference=reference).active().order_by("pk")
    ]


def _login_via_access_link(client: Client, customer: Customer, *, metadata: dict | None = None) -> None:
    _link, raw_token = AccessLink.create_with_token(
        customer_id=customer.uuid,
        audience=AccessLink.Audience.WEB_GENERAL,
        source=AccessLink.Source.INTERNAL,
        expires_at=timezone.now() + timedelta(minutes=5),
        metadata=metadata or {},
    )
    resp = client.post("/api/v1/auth/access/", {"token": raw_token})
    assert resp.status_code == 200, resp.content
    assert client.session.get("_auth_user_id"), "login deveria ter autenticado"


def _checkout_today(client: Client, *, phone: str = "+5543999990001"):
    """Checkout de retirada com a data de HOJE (a data JÁ EXISTE no checkout)."""
    from shopman.storefront.services.pickup_slots import get_slots

    slots = get_slots()
    assert slots, "esperava slots de retirada configurados por padrão"
    return client.post(
        "/api/v1/checkout/",
        data=json.dumps(
            {
                "name": "Pablo QA",
                "phone": phone,
                "fulfillment_type": "pickup",
                "delivery_date": timezone.localdate().isoformat(),
                "delivery_time_slot": slots[-1]["ref"],
                "payment_method": "cash",
            }
        ),
        content_type="application/json",
    )


def _assert_order_adopted(order: Order, expected_hold_ids: list[str]) -> None:
    """O pedido tem que ter adotado os holds da sacola — não criado novos."""
    adopted = [e["hold_id"] for e in order.data.get("hold_ids", []) if e.get("hold_id")]
    assert sorted(adopted) == sorted(expected_hold_ids), (
        f"commit não adotou os holds da sacola: sacola={expected_hold_ids} "
        f"pedido={adopted} (adoção zerada = fallback create_hold, o bug do QA)"
    )


# ── QA repro: add → login → checkout hoje → envio ────────────────────────────


def test_commit_adopts_planned_holds_after_access_link_login_same_browser(client):
    """Fluxo do QA no MESMO browser: o exchange preserva a cart_session_key e o
    commit adota os holds planejados criados antes do login."""
    _seed_planned_bakery(planned_qty=2)
    customer = _customer()

    cart_key = _add_to_cart(client, qty=2)
    hold_ids = _active_hold_ids(cart_key)
    assert hold_ids, "add com fornada planejada deveria ter criado holds planejados"
    planned = Hold.objects.filter(metadata__reference=cart_key).active()
    assert all(h.expires_at is None for h in planned), "hold planejado é indefinido"

    _login_via_access_link(client, customer)
    assert client.session.get("cart_session_key") == cart_key

    resp = _checkout_today(client)
    assert resp.status_code == 201, resp.content

    order = Order.objects.get(ref=resp.json()["order_ref"])
    _assert_order_adopted(order, hold_ids)


def test_commit_adopts_planned_holds_after_access_link_login_new_browser(client):
    """Fluxo do QA via in-app browser (WhatsApp): sessão Django NOVA, sacola
    adotada pela metadata do token (``cart_session_key``). O commit no novo
    browser tem que adotar os MESMOS holds planejados."""
    _seed_planned_bakery(planned_qty=2)
    customer = _customer()

    cart_key = _add_to_cart(client, qty=2)
    hold_ids = _active_hold_ids(cart_key)
    assert hold_ids

    in_app = Client()  # cookie jar novo — a sessão do site não existe aqui
    _login_via_access_link(in_app, customer, metadata={"cart_session_key": cart_key})
    assert in_app.session.get("cart_session_key") == cart_key

    resp = _checkout_today(in_app)
    assert resp.status_code == 201, resp.content

    order = Order.objects.get(ref=resp.json()["order_ref"])
    _assert_order_adopted(order, hold_ids)


def test_commit_adopts_planned_holds_after_otp_login(client):
    """Login por código (verify-code) também preserva a sacola e a adoção."""
    from shopman.doorman.models import VerificationCode
    from shopman.doorman.models.verification_code import generate_raw_code

    _seed_planned_bakery(planned_qty=2)
    _customer()

    cart_key = _add_to_cart(client, qty=2)
    hold_ids = _active_hold_ids(cart_key)
    assert hold_ids

    raw_code, digest = generate_raw_code()
    VerificationCode.objects.create(
        target_value="+5543999990001",
        purpose=VerificationCode.Purpose.LOGIN,
        code_hash=digest,
    )
    resp = client.post(
        "/api/v1/auth/verify-code/",
        data=json.dumps({"phone": "+5543999990001", "code": raw_code}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert client.session.get("cart_session_key") == cart_key

    resp = _checkout_today(client)
    assert resp.status_code == 201, resp.content

    order = Order.objects.get(ref=resp.json()["order_ref"])
    _assert_order_adopted(order, hold_ids)


# ── O fantasma do QA: rounds repetidos com o MESMO telefone ─────────────────


def test_second_round_same_phone_not_blocked_by_abandoned_session_ghost_holds(client):
    """Round 1 tenta o checkout e falha; round 2 (mesmo telefone) faz o pedido.

    O cenário real do QA staging: o round de 17:29 (``SESS-P8V2TWA4RAHW``)
    chegou ao checkout — ``assign_phone_handle`` colou o telefone na sessão —
    e falhou; os holds planejados dele (eternos, ``expires_at=None``) ficaram
    ativos. No round seguinte, ``assign_phone_handle(abandon_existing=True)``
    abandona a Session antiga e tem que LIBERAR os holds dela — senão o
    cliente compete com o próprio fantasma pela fornada do dia.
    """
    _seed_planned_bakery(planned_qty=4)
    customer = _customer()

    # Round 1: sacola com holds planejados; o checkout falha DEPOIS do
    # assign_phone_handle (guarda de total: o total exibido "mudou").
    round1 = Client()
    _login_via_access_link(round1, customer)
    round1_key = _add_to_cart(round1, qty=2)
    ghost_ids = _active_hold_ids(round1_key)
    assert ghost_ids

    from shopman.storefront.services.pickup_slots import get_slots

    resp = round1.post(
        "/api/v1/checkout/",
        data=json.dumps(
            {
                "name": "Pablo QA",
                "phone": "+5543999990001",
                "fulfillment_type": "pickup",
                "delivery_date": timezone.localdate().isoformat(),
                "delivery_time_slot": get_slots()[-1]["ref"],
                "payment_method": "cash",
                "expected_total_q": 1,
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code != 201, "setup: o checkout do round 1 devia falhar"
    assert _active_hold_ids(round1_key) == ghost_ids, (
        "setup: o commit falho do round 1 devia deixar os holds ativos"
    )

    # Round 2: outro browser, mesmo cliente/telefone.
    round2 = Client()
    _login_via_access_link(round2, customer)
    round2_key = _add_to_cart(round2, qty=2)
    assert round2_key != round1_key
    round2_hold_ids = _active_hold_ids(round2_key)

    resp = _checkout_today(round2)
    assert resp.status_code == 201, (
        f"round 2 foi bloqueado pelos holds fantasmas do round 1: {resp.content}"
    )

    order = Order.objects.get(ref=resp.json()["order_ref"])
    _assert_order_adopted(order, round2_hold_ids)

    # E os fantasmas do round 1 não podem continuar segurando o plano do dia.
    still_active = Hold.objects.filter(
        pk__in=[int(h.split(":")[1]) for h in ghost_ids],
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
    ).count()
    assert still_active == 0, (
        "sessão abandonada por assign_phone_handle deixou holds planejados "
        "eternos segurando a fornada do dia"
    )


def test_trusted_device_login_preserves_cart_when_session_flushes(client, monkeypatch):
    """Troca de usuário via trusted-device: o ``login()`` dá flush na sessão
    (outro usuário estava logado) e a sacola anônima tem que sobreviver —
    mesma garantia dos fluxos de access link e OTP."""
    from django.contrib.auth import get_user_model
    from shopman.doorman.services.device_trust import DeviceTrustService

    _seed_planned_bakery()
    _customer()

    other = get_user_model().objects.create_user(username="outro-usuario", password="x")
    client.force_login(other)
    session = client.session
    session["cart_session_key"] = "cart-anon-flush"
    session.save()

    monkeypatch.setattr(
        DeviceTrustService, "check_device_trust", classmethod(lambda cls, request, cid: True)
    )
    resp = client.post(
        "/api/v1/auth/device-check/",
        data=json.dumps({"phone": "+5543999990001"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["trusted"] is True

    assert client.session.get("cart_session_key") == "cart-anon-flush", (
        "flush do login() de trusted-device perdeu a sacola anônima"
    )


# ── QA repro fiel (staging 2026-07-14 19:58 UTC): checkout para AMANHÃ ───────


def test_checkout_tomorrow_with_todays_planned_batch_is_accepted_as_preorder(
    client, django_capture_on_commit_callbacks
):
    """A reprodução EXATA do commit falho do QA (evidência do DB staging:
    ``SESS-S37K9EYXUGUH``, ``delivery_date=2026-07-15``, fornada só em 14/07).

    ``stock.hold``: data futura desliga a adoção (``adopt_session_holds`` só
    para hoje) e o fallback ``create_hold(target=amanhã)`` recusa com
    INSUFFICIENT_AVAILABLE porque não há plano para amanhã — política
    ``planned_ok``. Resultado atual: "BAGUETE ficou indisponível antes de
    concluirmos a sua reserva" — beco sem saída.

    Comportamento esperado (decisão de produto, §2 do plano): encomenda
    antecipada é cidadã de 1ª classe — o canal web permite encomenda
    (``max_preorder_days`` já governa o checkout), então o commit com data
    futura REGISTRA a demanda em vez de recusar. Contrato observável:

    1. o envio do pedido é aceito (201);
    2. os holds planejados de HOJE da sacola não ficam órfãos — o pedido é
       para amanhã, então ou são adotados/re-datados pelo pedido ou liberados.
    """
    _seed_planned_bakery(planned_qty=2)
    customer = _customer()

    cart_key = _add_to_cart(client, qty=2)
    session_hold_ids = _active_hold_ids(cart_key)
    assert session_hold_ids, "sacola em lista de espera deveria ter holds planejados"

    _login_via_access_link(client, customer)
    assert client.session.get("cart_session_key") == cart_key

    from shopman.storefront.services.pickup_slots import get_slots

    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    resp = client.post(
        "/api/v1/checkout/",
        data=json.dumps(
            {
                "name": "Pablo QA",
                "phone": "+5543999990001",
                "fulfillment_type": "pickup",
                "delivery_date": tomorrow,
                "delivery_time_slot": get_slots()[0]["ref"],
                "payment_method": "cash",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 201, (
        f"encomenda para amanhã foi recusada (o commit falho do QA): {resp.content}"
    )

    order = Order.objects.get(ref=resp.json()["order_ref"])
    assert order.data.get("is_preorder") is True

    # Nenhum hold da sacola pode sobrar ativo referenciando a sessão: o commit
    # resolve todos (adota/re-data ou libera) — sem fantasmas eternos.
    assert _active_hold_ids(cart_key) == [], (
        "commit deixou holds planejados eternos órfãos na sessão"
    )

    # A demanda ficou REGISTRADA na data-alvo: hold de demanda (quant=None,
    # sem TTL até materializar), dono = pedido, com prioridade de pedido.
    order_holds = [
        Hold.objects.get(pk=int(e["hold_id"].split(":")[1]))
        for e in order.data["hold_ids"]
        if e.get("hold_id")
    ]
    assert order_holds, "encomenda sem demanda registrada não alimenta a produção"
    for hold in order_holds:
        assert hold.quant is None, "sem plano p/ amanhã, o hold é de DEMANDA"
        assert hold.target_date.isoformat() == tomorrow
        assert hold.expires_at is None
        assert hold.metadata.get("reference") == f"order:{order.ref}"
        assert hold.metadata.get("priority") == 0, "pedido enviado > sacola na fila"

    # O trabalho físico espera o dia: ao CONFIRMAR (confirmação otimista),
    # nada de ticket KDS hoje — o despertador (directive preorder.activate)
    # fica agendado para a madrugada da data.
    from shopman.orderman.models import Directive
    from shopman.orderman.models import Order as OrderModel

    from shopman.backstage.models import KDSTicket

    order.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        order.transition_status(OrderModel.Status.CONFIRMED, actor="test:operator")

    assert not KDSTicket.objects.filter(session_key=order.session_key).exists(), (
        "pedido de amanhã não pode disparar pra cozinha hoje"
    )
    order.refresh_from_db()
    assert order.status == OrderModel.Status.CONFIRMED, (
        "encomenda não pode virar PREPARING antes da data"
    )
    alarm = Directive.objects.filter(
        topic="preorder.activate", payload__order_ref=order.ref
    ).first()
    assert alarm is not None, "encomenda confirmada sem despertador na data"
    assert timezone.localtime(alarm.available_at).date().isoformat() == tomorrow
