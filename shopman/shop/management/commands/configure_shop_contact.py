"""Configure public shop contact fields for storefront and release readiness."""

from __future__ import annotations

import os

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from shopman.shop.models import Shop
from shopman.shop.models.shop import SHOP_CACHE_KEY


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _normalize_br_phone(value: str, *, field: str) -> str:
    digits = _digits(value)
    if not digits:
        raise CommandError(f"{field} precisa conter dígitos.")
    if not digits.startswith("55"):
        digits = f"55{digits}"
    if not 12 <= len(digits) <= 13:
        raise CommandError(f"{field} deve ficar em E.164 BR sem '+', ex: 554333231997.")
    return digits


def _whatsapp_url(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith(("https://wa.me/", "https://www.whatsapp.com/", "https://api.whatsapp.com/")):
        return stripped
    return f"https://wa.me/{_normalize_br_phone(stripped, field='WhatsApp')}"


def _without_whatsapp_links(links: list[str]) -> list[str]:
    return [
        link for link in links
        if "wa.me" not in link and "whatsapp.com" not in link
    ]


class Command(BaseCommand):
    help = "Configure Shop phone/email/WhatsApp contact used by storefront projections."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="", help="Shop name when a singleton must be created. Defaults to SHOPMAN_SHOP_NAME.")
        parser.add_argument("--phone", default="", help="Public shop phone, E.164 BR with or without '+'. Defaults to SHOPMAN_SHOP_PHONE.")
        parser.add_argument("--email", default="", help="Public shop email. Defaults to SHOPMAN_SHOP_EMAIL.")
        parser.add_argument("--whatsapp", default="", help="WhatsApp number or wa.me/api.whatsapp.com URL. Defaults to SHOPMAN_SHOP_WHATSAPP.")
        parser.add_argument("--dry-run", action="store_true", help="Print the resulting contact without saving.")

    def handle(self, *args, **options):
        shop = Shop.load() or Shop.objects.order_by("pk").first()
        if shop is None:
            name = (options["name"] or os.environ.get("SHOPMAN_SHOP_NAME", "") or "").strip()
            if not name:
                raise CommandError("Nenhuma loja existe. Informe --name para criar o singleton.")
            shop = Shop(name=name, brand_name=name)

        phone_input = options["phone"] or os.environ.get("SHOPMAN_SHOP_PHONE", "")
        email_input = options["email"] or os.environ.get("SHOPMAN_SHOP_EMAIL", "")
        whatsapp_input = options["whatsapp"] or os.environ.get("SHOPMAN_SHOP_WHATSAPP", "")

        phone = _normalize_br_phone(phone_input, field="Telefone") if phone_input else shop.phone
        email = (email_input or shop.email or "").strip()
        whatsapp_source = whatsapp_input or phone
        whatsapp = _whatsapp_url(whatsapp_source) if whatsapp_source else ""

        social_links = _without_whatsapp_links(list(shop.social_links or []))
        if whatsapp:
            social_links.insert(0, whatsapp)

        if options["dry_run"]:
            self.stdout.write(f"shop={shop.brand_name or shop.name or options['name']}")
            self.stdout.write(f"phone={phone or '-'}")
            self.stdout.write(f"email={email or '-'}")
            self.stdout.write(f"whatsapp_url={whatsapp or '-'}")
            return

        with transaction.atomic():
            if not shop.pk:
                shop.save()
            shop.phone = phone
            shop.email = email
            shop.social_links = social_links
            shop.save(update_fields=["phone", "email", "social_links"])

        cache.delete(SHOP_CACHE_KEY)
        self.stdout.write(self.style.SUCCESS(
            f"configure_shop_contact: contato atualizado para '{shop.brand_name or shop.name}'."
        ))
        if whatsapp:
            self.stdout.write(f"configure_shop_contact: WhatsApp público {whatsapp}.")
