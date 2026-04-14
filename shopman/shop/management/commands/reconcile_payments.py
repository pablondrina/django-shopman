"""
Management command: reconcile_payments

Reconcilia pedidos com status pending_payment cujo webhook de pagamento
pode ter sido perdido (timeout, reinicialização de servidor, falha de rede).

Lógica:
  1. Busca Orders com status=pending_payment criadas antes de `--since` atrás.
  2. Para cada uma, lê intent_ref em order.data["payment"].
  3. Consulta Payman: PaymentService.get(intent_ref).
  4. Se intent.status == "captured" → chama flow.on_paid(order) via transição.
  5. Se intent.status == "expired"  → chama flow.on_payment_expired(order) via transição.
  6. Loga cada reconciliação com order.ref, intent_ref, action.

Idempotente: rodar duas vezes não gera estado inconsistente.

Usage:
    python manage.py reconcile_payments
    python manage.py reconcile_payments --since=4h
    python manage.py reconcile_payments --since=30m --dry-run
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

_SINCE_PATTERN = re.compile(r"^(\d+)(m|h|d)$")


def _parse_since(value: str) -> timedelta:
    """Parse '2h', '30m', '1d' → timedelta."""
    m = _SINCE_PATTERN.match(value.strip().lower())
    if not m:
        raise ValueError(f"Formato inválido para --since: '{value}'. Use ex: 2h, 30m, 1d.")
    amount, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


class Command(BaseCommand):
    help = "Reconcilia pedidos pending_payment cujo webhook pode ter sido perdido."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            default="2h",
            help="Reconcilia pedidos criados antes de N tempo atrás (ex: 2h, 30m, 1d). Default: 2h.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas lista o que seria feito, sem executar.",
        )

    def handle(self, *args, **options):
        from shopman.orderman.models import Order

        since_str = options["since"]
        dry_run = options["dry_run"]

        try:
            since_delta = _parse_since(since_str)
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        cutoff = timezone.now() - since_delta

        pending = Order.objects.filter(
            status=Order.Status.CONFIRMED,
            created_at__lt=cutoff,
        )

        if not pending.exists():
            self.stdout.write("Nenhum pedido pending_payment encontrado para reconciliar.")
            return

        reconciled = 0
        skipped = 0

        for order in pending:
            payment_data = (order.data or {}).get("payment", {})
            intent_ref = payment_data.get("intent_ref")

            if not intent_ref:
                skipped += 1
                logger.debug("reconcile_payments: order %s sem intent_ref, ignorando.", order.ref)
                continue

            try:
                from shopman.payman import PaymentService
                intent = PaymentService.get(intent_ref)
            except Exception as exc:
                logger.warning(
                    "reconcile_payments: falha ao consultar intent %s (order %s): %s",
                    intent_ref, order.ref, exc,
                )
                skipped += 1
                continue

            if intent.status == "captured":
                action = "on_paid → flow dispatch"
                if not dry_run:
                    try:
                        from shopman.shop.lifecycle import dispatch
                        dispatch(order, "on_paid")
                        logger.info(
                            "reconcile_payments: order %s intent %s → on_paid dispatched",
                            order.ref, intent_ref,
                        )
                    except Exception as exc:
                        logger.error(
                            "reconcile_payments: falha ao despachar on_paid para order %s: %s",
                            order.ref, exc,
                        )
                        skipped += 1
                        continue
                reconciled += 1

            elif intent.status == "expired":
                action = "on_payment_expired → cancelled"
                if not dry_run:
                    try:
                        order.transition_status(Order.Status.CANCELLED, actor="reconcile_payments")
                        logger.info(
                            "reconcile_payments: order %s intent %s → cancelled (expired)",
                            order.ref, intent_ref,
                        )
                    except Exception as exc:
                        logger.error(
                            "reconcile_payments: falha ao cancelar order %s: %s",
                            order.ref, exc,
                        )
                        skipped += 1
                        continue
                reconciled += 1

            else:
                action = f"sem ação (intent.status={intent.status})"
                skipped += 1

            prefix = "[dry-run] " if dry_run else ""
            self.stdout.write(
                f"{prefix}order={order.ref} intent={intent_ref} → {action}"
            )

        summary = f"Reconciliados: {reconciled} | Ignorados: {skipped}"
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[dry-run] {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
