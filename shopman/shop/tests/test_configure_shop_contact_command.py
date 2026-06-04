from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.shop.models import Shop


@pytest.mark.django_db
def test_configure_shop_contact_sets_phone_and_whatsapp_link():
    shop = Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        social_links=["https://instagram.com/nelson", "https://wa.me/5500000000000"],
    )

    call_command(
        "configure_shop_contact",
        phone="(43) 3323-1997",
        email="contato@nelson.example",
        stdout=StringIO(),
    )

    shop.refresh_from_db()
    assert shop.phone == "554333231997"
    assert shop.email == "contato@nelson.example"
    assert shop.social_links == [
        "https://wa.me/554333231997",
        "https://instagram.com/nelson",
    ]


@pytest.mark.django_db
def test_configure_shop_contact_accepts_explicit_whatsapp_url():
    shop = Shop.objects.create(name="Loja", phone="5543999990000")

    call_command(
        "configure_shop_contact",
        whatsapp="https://api.whatsapp.com/send?phone=554333231997",
        stdout=StringIO(),
    )

    shop.refresh_from_db()
    assert shop.phone == "5543999990000"
    assert shop.social_links[0] == "https://api.whatsapp.com/send?phone=554333231997"


@pytest.mark.django_db
def test_configure_shop_contact_dry_run_does_not_save():
    shop = Shop.objects.create(name="Loja", phone="")
    output = StringIO()

    call_command(
        "configure_shop_contact",
        phone="554333231997",
        dry_run=True,
        stdout=output,
    )

    shop.refresh_from_db()
    assert shop.phone == ""
    assert "whatsapp_url=https://wa.me/554333231997" in output.getvalue()


@pytest.mark.django_db
def test_configure_shop_contact_reads_environment_defaults(monkeypatch):
    shop = Shop.objects.create(name="Loja")
    monkeypatch.setenv("SHOPMAN_SHOP_PHONE", "554333231997")
    monkeypatch.setenv("SHOPMAN_SHOP_EMAIL", "contato@nelson.example")

    call_command("configure_shop_contact", stdout=StringIO())

    shop.refresh_from_db()
    assert shop.phone == "554333231997"
    assert shop.email == "contato@nelson.example"
    assert shop.whatsapp_url == "https://wa.me/554333231997"


@pytest.mark.django_db
def test_configure_shop_contact_rejects_invalid_phone():
    Shop.objects.create(name="Loja")

    with pytest.raises(CommandError):
        call_command(
            "configure_shop_contact",
            phone="123",
            stdout=StringIO(),
        )
