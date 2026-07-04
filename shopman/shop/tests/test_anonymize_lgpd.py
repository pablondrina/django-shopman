"""Anonimização LGPD alcança a FONTE DE VERDADE do PII.

Regressão P1: anonymize_customer limpava só os campos denormalizados
(name/email/phone/birthday/notes), deixando intactos os ContactPoint (fonte de
verdade de telefone/e-mail), o document (CPF/CNPJ), o metadata e as identidades
externas — ou seja, o PII permanecia no banco.
"""

from __future__ import annotations

import pytest

from shopman.guestman.models import ContactPoint, Customer
from shopman.shop.services.account import anonymize_customer

pytestmark = pytest.mark.django_db


def test_anonymize_scrubs_source_of_truth_pii():
    c = Customer.objects.create(
        ref="CLI-ANON",
        first_name="Ana",
        last_name="Silva",
        phone="+5543999990000",
        email="ana@example.com",
        document="529.982.247-25",
        metadata={"pref": "sem lactose"},
    )
    # O save() sincroniza ContactPoints a partir de phone/email.
    assert ContactPoint.objects.filter(customer=c).exists()

    anonymize_customer(c)

    c.refresh_from_db()
    assert c.first_name == "Anonimizado"
    assert c.last_name == ""
    assert c.email == ""
    assert c.phone == ""
    assert c.is_active is False
    # A fonte de verdade e os identificadores fiscais/contextuais também somem.
    assert c.document == ""
    assert c.metadata == {}
    assert not ContactPoint.objects.filter(customer=c).exists()


def test_anonymize_is_idempotent():
    c = Customer.objects.create(
        ref="CLI-ANON-2", first_name="Beto", phone="+5543999990001", document="111"
    )
    anonymize_customer(c)
    # Rodar de novo não deve estourar (defensivo por camada).
    anonymize_customer(c)
    c.refresh_from_db()
    assert c.document == ""
    assert not ContactPoint.objects.filter(customer=c).exists()
