"""Re-despacha fases de lifecycle perdidas por crash pós-commit.

O lifecycle não é durável: ``order_changed`` → ``transaction.on_commit(dispatch)``
roda síncrono no processo. Um crash/deploy entre o COMMIT da transição e o fim
do handler perde a fase inteira — sem hold (on_commit), sem ticket KDS/baixa de
estoque (on_confirmed/on_paid), sem devolução de estoque/estorno (on_cancelled).

Um dispatch completo grava ``order.data["lifecycle"][fase] = "done"``
(``DURABLE_PHASES`` em shopman/shop/lifecycle.py). Este sweeper acha pedidos
parados além do limiar SEM o marcador da fase do seu status e re-despacha — os
handlers são idempotentes (hold via presença de hold_ids, fulfill via state
machine do Hold, tickets KDS por delta de line_id, notificação via dedupe de
directive, pagamento via intent/captured_at):

  * NEW sem on_commit           → dispatch("on_commit")
  * CONFIRMED sem on_confirmed  → dispatch("on_confirmed")
  * NEW/CONFIRMED pagos (captured_at ou Payman suficiente) sem on_paid
                                → dispatch("on_paid")
  * CANCELLED sem on_cancelled  → dispatch("on_cancelled")

Cada pedido é re-despachado para NO MÁXIMO uma fase por ciclo (na ordem do
lifecycle); o marcador gravado no re-dispatch garante que pedidos saudáveis
(inclusive os anteriores a este marcador) são varridos uma única vez.

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
    help = "Re-despacha fases de lifecycle incompletas (crash pós-commit)."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=15, help="Idade mínima parado (default 15).")
        parser.add_argument("--dry-run", action="store_true", help="Só reporta, não re-despacha.")

    def handle(self, *args, **options):
        from shopman.orderman.models import Order

        cutoff = timezone.now() - timedelta(minutes=max(1, int(options["minutes"])))
        self._dry_run = bool(options["dry_run"])
        self._recovered = 0
        self._swept_refs: set[str] = set()

        # NEW sem on_commit: created_at é o instante da fase perdida.
        self._sweep_phase(
            Order.objects.filter(status=Order.Status.NEW, created_at__lt=cutoff),
            phase="on_commit",
        )

        # CONFIRMED sem on_confirmed: updated_at cobre a transição (evita varrer
        # pedido recém-confirmado cujo dispatch ainda está rodando).
        self._sweep_phase(
            Order.objects.filter(status=Order.Status.CONFIRMED, updated_at__lt=cutoff),
            phase="on_confirmed",
        )

        # Pagos sem on_paid: o carimbo durável (payment.captured_at, gravado
        # ANTES do dispatch em todos os caminhos de captura) ou o Payman
        # (intent capturada — caminho Stripe) provam que a fase deveria ter
        # rodado. Fora de NEW/CONFIRMED o trabalho do on_paid já aconteceu por
        # outra fase.
        self._sweep_phase(
            Order.objects.filter(
                status__in=(Order.Status.NEW, Order.Status.CONFIRMED),
                updated_at__lt=cutoff,
            ),
            phase="on_paid",
            extra_guard=self._payment_captured,
        )

        # CANCELLED sem on_cancelled: estoque preso, estorno e aviso pendentes.
        self._sweep_phase(
            Order.objects.filter(status=Order.Status.CANCELLED, updated_at__lt=cutoff),
            phase="on_cancelled",
        )

        if self._recovered:
            self.stdout.write(
                self.style.WARNING(
                    f"sweep_stuck_orders: {self._recovered} fase(s) incompleta(s) "
                    f"{'detectada(s)' if self._dry_run else 're-despachada(s)'}."
                )
            )

    def _sweep_phase(self, queryset, *, phase: str, extra_guard=None) -> None:
        from shopman.shop.lifecycle import dispatch, phase_complete

        for order in queryset.iterator():
            if order.ref in self._swept_refs:
                continue  # já re-despachado numa fase anterior neste ciclo
            if phase_complete(order, phase):
                continue
            if extra_guard is not None and not extra_guard(order):
                continue

            logger.warning(
                "sweep_stuck_orders: pedido %s com fase %s incompleta (status=%s)",
                order.ref,
                phase,
                order.status,
            )
            self._swept_refs.add(order.ref)
            if self._dry_run:
                self._recovered += 1
                continue

            try:
                dispatch(order, phase)
                self._recovered += 1
            except Exception:
                logger.exception(
                    "sweep_stuck_orders: re-dispatch de %s falhou para %s", phase, order.ref
                )
                self._alert(order, phase)

    def _payment_captured(self, order) -> bool:
        """True quando há captura suficiente registrada para o pedido."""
        payment = (order.data or {}).get("payment") or {}
        if payment.get("captured_at"):
            return True
        if not payment.get("intent_ref"):
            return False
        try:
            from shopman.shop.services import payment as payment_service

            return payment_service.has_sufficient_captured_payment(order) is True
        except Exception:
            logger.warning(
                "sweep_stuck_orders: consulta de pagamento falhou order=%s", order.ref, exc_info=True
            )
            return False

    def _alert(self, order, phase: str) -> None:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="lifecycle_phase_stuck",
            severity="critical",
            message=(
                f"Pedido {order.ref} ficou com a fase {phase} incompleta e o "
                "re-dispatch automático falhou — conferir e destravar manualmente."
            ),
            order_ref=order.ref,
            dedupe_key=f"lifecycle_phase_stuck:{order.ref}:{phase}",
        )
