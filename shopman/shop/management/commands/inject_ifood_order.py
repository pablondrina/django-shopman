"""Injeta um pedido iFood simulado pela porta canônica de ingestão (DEV).

Uso local, gated por DEBUG: monta um payload iFood mínimo com o primeiro
produto real do Offerman (para passar as checagens de estoque/preço de ponta a
ponta) e o ingere via ``ifood_ingest.ingest`` no canal iFood.
"""

from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Injeta um pedido iFood simulado pela ingestão canônica (apenas DEBUG)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Comando disponível apenas com DEBUG=True.")

        from shopman.offerman.models import Product

        from shopman.shop.models import Channel
        from shopman.shop.services import ifood_ingest

        channel_ref = ifood_ingest.IFOOD_CHANNEL_REF
        if not Channel.objects.filter(ref=channel_ref).exists():
            raise CommandError(f"Canal '{channel_ref}' não existe — rode o seed antes.")

        product = (
            Product.objects.filter(is_published=True, is_sellable=True)
            .exclude(base_price_q=0)
            .first()
        )
        if product is None:
            raise CommandError("Nenhum produto ativo com preço — rode o seed antes.")

        order_code = f"IFOOD-DEV-{uuid4().hex[:8].upper()}"
        payload = {
            "order_code": order_code,
            "merchant_id": "mock-merchant",
            "created_at": timezone.now().isoformat(),
            "customer": {
                "name": "Cliente iFood Simulado (DEV)",
                "phone": "",
            },
            "delivery": {
                "type": "DELIVERY",
                "address": "Rua Simulada, 123 — Bairro iFood",
            },
            "items": [
                {
                    "sku": product.sku,
                    "name": product.name,
                    "qty": 1,
                    "unit_price_q": product.base_price_q,
                },
            ],
            "notes": "[SIMULAÇÃO] Pedido injetado via inject_ifood_order",
        }

        try:
            order = ifood_ingest.ingest(payload, channel_ref=channel_ref)
        except ifood_ingest.IFoodIngestError as e:
            raise CommandError(f"Falha ao injetar em {channel_ref}: {e.message}") from e

        self.stdout.write(self.style.SUCCESS(f"Pedido iFood simulado criado: {order.ref}"))
