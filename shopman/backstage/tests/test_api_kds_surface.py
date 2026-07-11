"""Headless KDS API contract (api/v1/backstage/kds/*).

Migrates the behavioural coverage of the retired KDS-HTMX views (station +
customer board) onto the REST surface that the canonical kds-nuxt app
consumes. Gate is the real ``backstage.operate_kds`` permission (granted to the
Cozinha group); the customer pickup board is public.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket


def _operate_kds_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(KDSTicket),
        codename="operate_kds",
    )


@pytest.fixture
def kds_operator(db):
    user = User.objects.create_user("kds-api", password="pw", is_staff=True)
    user.user_permissions.add(_operate_kds_perm())
    return user


@pytest.fixture
def kds_setup(db):
    prep = KDSInstance.objects.create(ref="prep-api", name="Preparo API", type="prep", target_time_minutes=10)
    expedition = KDSInstance.objects.create(ref="exp-api", name="Expedição API", type="expedition")
    order = Order.objects.create(
        ref="KDS-API-1",
        channel_ref="web",
        session_key="sk-kds-api-1",
        status=Order.Status.CONFIRMED,
        total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup"},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=1500, line_total_q=1500)
    ticket = KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=prep,
        items=[{"sku": "SKU", "name": "Produto", "qty": 1, "notes": "Sem sal", "checked": False}],
    )
    ready = Order.objects.create(
        ref="KDS-API-READY",
        channel_ref="web",
        status=Order.Status.READY,
        total_q=2000,
        data={"customer": {"name": "Bia"}, "fulfillment_type": "pickup"},
    )
    OrderItem.objects.create(order=ready, line_id="2", sku="SKU2", name="Produto 2", qty=2, unit_price_q=1000, line_total_q=2000)
    return prep, expedition, ticket, ready


# ── Gate ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_index_requires_staff(client, db, kds_setup):
    # index is staff-gated (IsBackstageOperator); non-staff blocked, staff allowed
    customer = User.objects.create_user("cust", password="pw", is_staff=False)
    client.force_login(customer)
    assert client.get(reverse("api-backstage-kds-index")).status_code == 403
    staff = User.objects.create_user("staff-only", password="pw", is_staff=True)
    client.force_login(staff)
    assert client.get(reverse("api-backstage-kds-index")).status_code == 200


@pytest.mark.django_db
def test_board_requires_operate_kds(client, db, kds_setup):
    prep = kds_setup[0]
    bare = User.objects.create_user("bare2", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-kds-board", args=[prep.ref])).status_code == 403


# ── Read ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_index_lists_instances(client, kds_operator, kds_setup):
    client.force_login(kds_operator)
    response = client.get(reverse("api-backstage-kds-index"))
    assert response.status_code == 200
    refs = {i["ref"] for i in response.json()["instances"]}
    assert {"prep-api", "exp-api"} <= refs


@pytest.mark.django_db
def test_board_returns_tickets(client, kds_operator, kds_setup):
    prep = kds_setup[0]
    client.force_login(kds_operator)
    response = client.get(reverse("api-backstage-kds-board", args=[prep.ref]))
    assert response.status_code == 200
    board = response.json()["board"]
    assert board["instance_ref"] == "prep-api"
    assert len(board["tickets"]) == 1


# ── Write actions ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_item_check_toggles_and_is_idempotent(client, kds_operator, kds_setup):
    ticket = kds_setup[2]
    client.force_login(kds_operator)
    url = reverse("api-backstage-kds-ticket-item", args=[ticket.pk])
    r1 = client.post(url, data={"index": 0, "checked": True}, content_type="application/json")
    assert r1.status_code == 200
    assert r1.json()["ticket"]["items"][0]["checked"] is True
    # idempotent re-check
    r2 = client.post(url, data={"index": 0, "checked": True}, content_type="application/json")
    assert r2.status_code == 200


@pytest.mark.django_db
def test_item_check_rejects_bad_index(client, kds_operator, kds_setup):
    ticket = kds_setup[2]
    client.force_login(kds_operator)
    url = reverse("api-backstage-kds-ticket-item", args=[ticket.pk])
    assert client.post(url, data={"index": -1, "checked": True}, content_type="application/json").status_code == 400


@pytest.mark.django_db
def test_item_check_rejects_non_numeric_index(client, kds_operator, kds_setup):
    ticket = kds_setup[2]
    client.force_login(kds_operator)
    url = reverse("api-backstage-kds-ticket-item", args=[ticket.pk])
    response = client.post(url, data={"index": "abc", "checked": True}, content_type="application/json")
    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_ticket_done(client, kds_operator, kds_setup):
    ticket = kds_setup[2]
    client.force_login(kds_operator)
    response = client.post(reverse("api-backstage-kds-ticket-done", args=[ticket.pk]))
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.django_db
def test_ticket_done_replay_is_success(client, kds_operator, kds_setup):
    # Duas estações bumpando o mesmo ticket: o replay é sucesso no-op, nunca
    # um toast de erro espúrio na segunda estação.
    ticket = kds_setup[2]
    client.force_login(kds_operator)
    url = reverse("api-backstage-kds-ticket-done", args=[ticket.pk])
    assert client.post(url).status_code == 200
    again = client.post(url)
    assert again.status_code == 200
    assert again.json()["ok"] is True


@pytest.mark.django_db
def test_internal_bug_surfaces_as_500_not_400(kds_operator, kds_setup, monkeypatch):
    # Bug de programação não pode virar 400: o operator-kit trata 4xx como
    # não-retryável e a telemetria classifica como erro de cliente.
    from django.test import Client

    from shopman.backstage.api import kds as kds_api

    def boom(**kwargs):
        raise RuntimeError("bug interno")

    monkeypatch.setattr(kds_api.kds_service, "mark_ticket_done", boom)
    client = Client(raise_request_exception=False)
    client.force_login(kds_operator)
    response = client.post(reverse("api-backstage-kds-ticket-done", args=[kds_setup[2].pk]))
    assert response.status_code == 500


@pytest.mark.django_db
def test_expedition_action_validates_action(client, kds_operator, kds_setup):
    ready = kds_setup[3]
    client.force_login(kds_operator)
    url = reverse("api-backstage-kds-expedition", args=[ready.pk])
    assert client.post(url, data={"action": "bogus"}, content_type="application/json").status_code == 400
    ok = client.post(url, data={"action": "complete"}, content_type="application/json")
    assert ok.status_code == 200
    assert ok.json()["action"] == "complete"


@pytest.mark.django_db
def test_ticket_done_missing_ticket_is_404(client, kds_operator, kds_setup):
    # Recurso inexistente mapeia por TIPO (KDSTicketNotFound) para 404, não 400.
    client.force_login(kds_operator)
    response = client.post(reverse("api-backstage-kds-ticket-done", args=[999999]))
    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket não encontrado."


@pytest.mark.django_db
def test_expedition_missing_order_is_404(client, kds_operator, kds_setup):
    client.force_login(kds_operator)
    url = reverse("api-backstage-kds-expedition", args=[999999])
    response = client.post(url, data={"action": "complete"}, content_type="application/json")
    assert response.status_code == 404
    assert response.json()["detail"] == "Pedido não encontrado."


@pytest.mark.django_db
def test_expedition_propagates_specific_core_message(client, kds_operator, kds_setup):
    # Dispatch de pedido de retirada: a mensagem real do core chega ao
    # operador — nunca o genérico "Ação inválida".
    ready = kds_setup[3]  # pickup
    client.force_login(kds_operator)
    url = reverse("api-backstage-kds-expedition", args=[ready.pk])
    response = client.post(url, data={"action": "dispatch"}, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["detail"] == "Pedido de retirada não pode ser despachado"


@pytest.mark.django_db
def test_ticket_done_blocked_by_payment_gate_says_why(client, kds_operator, kds_setup):
    # Pedido CONFIRMED com PIX sem captura: o bump é barrado pelo gate de
    # pagamento e o operador lê a razão real, não "Ticket não está aberto."
    ticket = kds_setup[2]
    order = Order.objects.get(session_key=ticket.session_key)
    order.data = {**(order.data or {}), "payment": {"method": "pix"}}
    order.save(update_fields=["data"])
    client.force_login(kds_operator)
    response = client.post(reverse("api-backstage-kds-ticket-done", args=[ticket.pk]))
    assert response.status_code == 400
    assert "Pagamento ainda não foi confirmado" in response.json()["detail"]


# ── Customer board (public) ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_customer_board_rejects_non_numeric_limit(client, kds_setup):
    # endpoint público: ?limit=abc responde 400 limpo, nunca 500
    response = client.get(reverse("api-backstage-kds-customer"), {"limit": "abc"})
    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_customer_board_clamps_out_of_range_limit(client, kds_setup):
    assert client.get(reverse("api-backstage-kds-customer"), {"limit": "0"}).status_code == 200
    assert client.get(reverse("api-backstage-kds-customer"), {"limit": "100000"}).status_code == 200


@pytest.mark.django_db
def test_customer_board_is_public_and_privacy_safe(client, kds_setup):
    # no auth required
    response = client.get(reverse("api-backstage-kds-customer"))
    assert response.status_code == 200
    body = response.json()["status"]
    # ready pickup order shows; no PII (customer name) leaks into the board payload
    blob = str(body)
    assert "Bia" not in blob
