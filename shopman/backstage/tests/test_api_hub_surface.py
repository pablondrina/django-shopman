"""Central de Apps — contrato do launcher (GET /api/v1/backstage/hub/).

O endpoint é staff-gated (IsBackstageOperator); os tiles são filtrados por permissão
DENTRO da projection — operador sem apps recebe grade vazia (não 403). Ícone forte por
superfície conforme o design system canônico.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from shopman.shop.models import Shop


def _manage_orders_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Shop),
        codename="manage_orders",
    )


@pytest.mark.django_db
def test_hub_requires_staff(client, db):
    customer = User.objects.create_user("hub-cust", password="pw", is_staff=False)
    client.force_login(customer)
    assert client.get(reverse("api-backstage-hub")).status_code == 403

    staff = User.objects.create_user("hub-staff", password="pw", is_staff=True)
    client.force_login(staff)
    assert client.get(reverse("api-backstage-hub")).status_code == 200


@pytest.mark.django_db
def test_hub_empty_for_staff_without_apps(client, db):
    """Staff sem nenhuma permissão de operação → launcher sem tiles (não 403)."""
    staff = User.objects.create_user("hub-plain", password="pw", is_staff=True)
    client.force_login(staff)
    hub = client.get(reverse("api-backstage-hub")).json()["hub"]
    assert hub["tiles"] == []
    assert hub["operator_name"] == "hub-plain"


@pytest.mark.django_db
def test_hub_superuser_sees_all_tiles(client, db):
    admin = User.objects.create_superuser("hub-admin", "a@b.c", "pw")
    client.force_login(admin)
    hub = client.get(reverse("api-backstage-hub")).json()["hub"]

    refs = [tile["ref"] for tile in hub["tiles"]]
    assert refs == ["pos", "kds", "gestor", "production", "broadcast", "loja"]

    by_ref = {tile["ref"]: tile for tile in hub["tiles"]}
    # Ícone forte por app (DS §6).
    assert by_ref["pos"]["icon"] == "banknote"
    assert by_ref["kds"]["icon"] == "chef-hat"
    assert by_ref["gestor"]["icon"] == "clipboard-list"
    assert by_ref["production"]["icon"] == "croissant"
    assert by_ref["broadcast"]["icon"] == "megaphone"
    assert by_ref["loja"]["icon"] == "store"
    # Loja abre a loja do cliente (storefront) em nova aba — fora da zona de operador.
    assert by_ref["loja"]["kind"] == "external"
    assert by_ref["loja"]["url"] == "http://127.0.0.1:3000/"
    assert by_ref["pos"]["kind"] == "launch"
    # Contrato do tile.
    for tile in hub["tiles"]:
        assert set(tile) == {"ref", "label", "description", "icon", "url", "kind"}
        assert tile["label"] and tile["url"]


@pytest.mark.django_db
def test_hub_filters_by_permission(client, db):
    """Operador só de pedidos vê o Gestor, não o PDV/KDS/Loja."""
    operator = User.objects.create_user("hub-gestor", password="pw", is_staff=True)
    operator.user_permissions.add(_manage_orders_perm())
    client.force_login(operator)
    refs = [tile["ref"] for tile in client.get(reverse("api-backstage-hub")).json()["hub"]["tiles"]]

    assert "gestor" in refs
    assert "pos" not in refs
    assert "kds" not in refs
    assert "loja" not in refs  # loja só p/ superuser
