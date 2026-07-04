"""Resgata pedidos órfãos em NEW cujo on_commit nunca completou.

O lifecycle não é durável: ``order_changed`` → ``transaction.on_commit(dispatch)``
roda síncrono no processo. Um crash/deploy entre o COMMIT do pedido e o callback
perde a fase inteira — o pedido fica em NEW sem hold, sem confirmação, sem
notificação, e nada o recupera.

Um on_commit completo grava ``order.data["lifecycle"]["on_commit"] = "done"``. Este
sweeper acha os NEW mais velhos que um limiar SEM esse marcador e re-despacha a
fase on_commit — que é idempotente (stock.hold, loyalty, fulfillment, notification,
payment todos guardam repetição). Também alerta o operador (visibilidade).

Uso:
    python manage.py sweep_stuck_orders                 # limiar padrão 15 min
    python manage.py sweep_stuck_orders --minutes 30
    python manage.py sweep_stuck_orders --dry-run
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-despacha on_commit para pedidos órfãos em NEW (crash pós-commit)."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=15, help="Idade mínima em NEW (default 15).")
        parser.add_argument("--dry-run", action="store_true", help="Só reporta, não re-despacha.")

    def handle(self, *args, **options):
        from shopman.orderman.models import Order
        from shopman.shop.lifecycle import dispatch

        cutoff = timezone.now() - timedelta(minutes=max(1, int(options["minutes"])))
        dry_run = bool(options["dry_run"])

        stuck = Order.objects.filter(status=Order.Status.NEW, created_at__lt=cutoff)
        recovered = 0
        for order in stuck.iterator():
            marks = (order.data or {}).get("lifecycle", {})
            if marks.get("on_commit") == "done":
                continue  # fase completou; está só aguardando confirmação/timeout

            logger.warning(
                "sweep_stuck_orders: pedido %s órfão em NEW (on_commit não completou)",
                order.ref,
            )
            if dry_run:
                recovered += 1
                continue

            try:
                dispatch(order, "on_commit")
                recovered += 1
            except Exception:
                logger.exception("sweep_stuck_orders: re-dispatch falhou para %s", order.ref)
                self._alert(order)

        if recovered:
            self.stdout.write(
                self.style.WARNING(
                    f"sweep_stuck_orders: {recovered} pedido(s) órfão(s) "
                    f"{'detectado(s)' if dry_run else 're-despachado(s)'}."
                )
            )

    def _alert(self, order) -> None:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="order_stuck_new",
            severity="critical",
            message=(
                f"Pedido {order.ref} ficou preso em NEW e o re-dispatch automático "
                "falhou — conferir e destravar manualmente."
            ),
            order_ref=order.ref,
            dedupe_key=f"order_stuck_new:{order.ref}",
        )
