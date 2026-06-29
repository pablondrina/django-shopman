"""Teleporte — hand off a delivery order to the external courier (no-API service).

Local operator utility: extracts the order's structured delivery data into a clean,
paste-ready block and copies it to the clipboard, so the operator does not retype the
address into the courier's web form. Clipboard-fallback slice of WP-11 slice 3; the
``--json`` output is the seam for a future DOM auto-filler (see
DELIVERY-EXTERNAL-LOGISTICS-PLAN.md).

    python manage.py teleporte ORDER-REF          # print + copy to clipboard
    python manage.py teleporte ORDER-REF --json    # structured payload (for tooling)
    python manage.py teleporte ORDER-REF --no-copy  # print only
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.shop.services.dispatch_handoff import (
    NotDeliverableError,
    build_dispatch_payload,
    copy_to_clipboard,
    format_dispatch_text,
)


class Command(BaseCommand):
    help = "Teleporte: leva os dados de entrega de um pedido para a área de transferência (despacho manual)."

    def add_arguments(self, parser):
        parser.add_argument("ref", help="Order.ref do pedido de entrega.")
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emite o payload estruturado (para ferramentas/auto-fill), não o bloco de texto.",
        )
        parser.add_argument(
            "--no-copy",
            action="store_false",
            dest="copy",
            help="Não copiar para a área de transferência; apenas imprimir.",
        )

    def handle(self, *args, **options):
        from shopman.orderman.models import Order

        ref = str(options["ref"]).strip()
        try:
            order = Order.objects.get(ref=ref)
        except Order.DoesNotExist as exc:
            raise CommandError(f"Pedido não encontrado: {ref}") from exc

        try:
            payload = build_dispatch_payload(order)
        except NotDeliverableError as exc:
            raise CommandError(str(exc)) from exc

        if options["as_json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        text = format_dispatch_text(payload)
        self.stdout.write(text)

        if options["copy"]:
            if copy_to_clipboard(text):
                self.stdout.write(self.style.SUCCESS("\n✓ copiado para a área de transferência."))
            else:
                self.stdout.write(
                    "\n(área de transferência indisponível neste ambiente — copie o texto acima)"
                )
