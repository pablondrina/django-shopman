"""forget_customer — anonimização LGPD do lado do auth (doorman).

O bridge copia first_name/last_name do cliente para o Django User no login; a
anonimização precisa alcançá-los e revogar os dispositivos confiáveis, senão o
nome do cliente sobrevive no auth e os aparelhos seguem confiados.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from shopman.doorman.models import CustomerUser, TrustedDevice
from shopman.doorman.services._user_bridge import forget_customer

User = get_user_model()
pytestmark = pytest.mark.django_db


def test_forget_customer_scrubs_user_and_revokes_devices():
    cid = uuid.uuid4()
    user = User.objects.create_user(username="customer_x", first_name="Ana", last_name="Silva")
    user.email = "ana@example.com"
    user.save()
    CustomerUser.objects.create(user=user, customer_id=cid)
    TrustedDevice.create_for_customer(customer_id=cid, user_agent="A")
    TrustedDevice.create_for_customer(customer_id=cid, user_agent="B")

    forget_customer(cid)

    user.refresh_from_db()
    assert user.first_name == ""
    assert user.last_name == ""
    assert user.email == ""
    assert user.is_active is False
    assert TrustedDevice.objects.filter(customer_id=cid, is_active=True).count() == 0


def test_forget_customer_without_link_is_safe():
    # Cliente sem User vinculado (ex.: só pediu por WhatsApp) — não deve estourar.
    forget_customer(uuid.uuid4())
