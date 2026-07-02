"""
fiscal_emit — emite a NFC-e de um pedido em HOMOLOGAÇÃO, de ponta a ponta.

O "lampejo" ao vivo: pega um pedido concluído, marca ``fiscal.issue_document`` e roda o
handler de emissão contra o Focus NFe (homologação). Ao autorizar, guarda chave/protocolo/
DANFE/QR em ``order.data`` — e o cupom aparece em ``/fiscal/danfe/<ref>/``.

Requer o adapter fiscal ligado (``SHOPMAN_FISCAL_ADAPTER``) + token e CNPJ emitente
(``FOCUS_NFE_TOKEN`` / ``FOCUS_NFE_CNPJ_EMITENTE`` ou ``Shop.document``).

    python manage.py fiscal_emit --order WHATSAPP-260702-XXXX
    python manage.py fiscal_emit            # escolhe um pedido concluído com itens
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Emite a NFC-e de um pedido em homologação (ponta a ponta) e mostra o resultado."

    def add_arguments(self, parser):
        parser.add_argument("--order", dest="order_ref", default="", help="ref do pedido a emitir")

    def handle(self, *args, **options):
        from shopman.orderman.models import Directive, Order

        from shopman.shop.fiscal import fiscal_pool
        from shopman.shop.handlers.fiscal import NFCeEmitHandler
        from shopman.shop.services import fiscal as fiscal_service

        backend = fiscal_pool.get_backend()
        if backend is None:
            raise CommandError(
                "Nenhum backend fiscal configurado. Defina "
                "SHOPMAN_FISCAL_ADAPTER=shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend "
                "(+ FOCUS_NFE_TOKEN e FOCUS_NFE_CNPJ_EMITENTE ou Shop.document)."
            )

        order = self._pick_order(Order, options["order_ref"])
        self.stdout.write(f"  📄 Pedido {order.ref} · total {order.total_q} · {order.items.count()} item(ns)")

        # Marca a intenção fiscal (o operador opta por emitir) e garante um consumidor.
        data = order.data or {}
        data.setdefault("fiscal", {})["issue_document"] = True
        data.setdefault("customer", {}).setdefault("name", "Consumidor Final")
        data.setdefault("payment", {}).setdefault("method", "cash")
        order.data = data
        order.save(update_fields=["data", "updated_at"])

        fiscal_service.emit(order)
        directive = (
            Directive.objects.filter(topic="fiscal.emit_nfce", payload__order_ref=order.ref)
            .order_by("-id")
            .first()
        )
        if directive is None:
            raise CommandError("Directive de emissão não foi criada (issue_document/idempotência?).")

        self.stdout.write("  🏛  Emitindo contra SEFAZ (homologação)…")
        directive.attempts = 1
        NFCeEmitHandler(backend).handle(message=directive, ctx={})

        order.refresh_from_db()
        result = order.data or {}
        chave = result.get("nfce_access_key")
        if not chave:
            raise CommandError("Emissão não retornou chave de acesso (ver status/erro acima).")

        self.stdout.write(self.style.SUCCESS("  ✅ NFC-e autorizada em homologação"))
        self.stdout.write(f"     status:    {result.get('nfce_status')}")
        self.stdout.write(f"     chave:     {chave}")
        self.stdout.write(f"     protocolo: {result.get('nfce_protocol')}")
        self.stdout.write(f"     nº/série:  {result.get('nfce_number')}/{result.get('nfce_series')}")
        self.stdout.write(f"     DANFE:     {result.get('nfce_danfe_url')}")
        self.stdout.write(f"  🖨  Cupom (lampejo): /fiscal/danfe/{order.ref}/")

    def _pick_order(self, Order, order_ref: str):
        if order_ref:
            order = Order.objects.filter(ref=order_ref).first()
            if order is None:
                raise CommandError(f"Pedido '{order_ref}' não encontrado.")
            return order
        order = (
            Order.objects.filter(status="completed", data__nfce_access_key__isnull=True)
            .exclude(items=None)
            .order_by("-created_at")
            .first()
        )
        if order is None:
            raise CommandError("Nenhum pedido concluído sem NFC-e para emitir. Rode o seed antes.")
        return order
