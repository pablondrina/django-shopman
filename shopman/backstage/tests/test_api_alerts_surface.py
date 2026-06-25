"""Headless operator alerts API contract (api/v1/backstage/alerts/*).

The dedicated operator apps (Gestor, etc.) consume this instead of the legacy HTMX
alert fragments. Gate is ``can_view_operator_alerts`` (staff + any operator
capability), shared with the sidebar badge.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Shop


def _manage_orders_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_orders",
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(db, shop):
    user = User.objects.create_user("alerts-op", password="pw", is_staff=True)
    user.user_permissions.add(_manage_orders_perm())
    return user


@pytest.fixture
def alert(db):
    return OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo de Pão")


@pytest.mark.django_db
def test_list_requires_operator_capability(client, db, shop, alert):
    # staff WITHOUT any operator capability → blocked
    bare = User.objects.create_user("bare-staff", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-alerts")).status_code == 403


@pytest.mark.django_db
def test_list_blocks_non_staff(client, db, shop, alert):
    customer = User.objects.create_user("cust", password="pw", is_staff=False)
    client.force_login(customer)
    assert client.get(reverse("api-backstage-alerts")).status_code == 403


@pytest.mark.django_db
def test_list_returns_alerts_and_counts(client, operator, alert):
    OperatorAlert.objects.create(type="payment_failed", severity="critical", message="Pix falhou")
    client.force_login(operator)
    response = client.get(reverse("api-backstage-alerts"))
    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {"active": 2, "critical": 1}
    assert len(body["alerts"]) == 2
    first = body["alerts"][0]
    assert {"pk", "type", "type_label", "severity", "severity_label", "message", "created_at_display"} <= set(first)


@pytest.mark.django_db
def test_list_excludes_acknowledged(client, operator, alert):
    alert.acknowledged = True
    alert.save(update_fields=["acknowledged"])
    client.force_login(operator)
    body = client.get(reverse("api-backstage-alerts")).json()
    assert body["counts"]["active"] == 0
    assert body["alerts"] == []


@pytest.mark.django_db
def test_ack_marks_alert(client, operator, alert):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-alert-ack", args=[alert.pk]))
    assert response.status_code == 200
    assert response.json() == {"ok": True, "pk": alert.pk}
    alert.refresh_from_db()
    assert alert.acknowledged is True


@pytest.mark.django_db
def test_ack_unknown_is_404(client, operator):
    client.force_login(operator)
    assert client.post(reverse("api-backstage-alert-ack", args=[999999])).status_code == 404
