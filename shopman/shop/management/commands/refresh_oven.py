"""
Dev-only: refresh ALL time-sensitive seed data so the storefront, KDS, and
order screens show realistic, recent activity.

Covers:
1. **Production Moves** — spreads timestamps across the last hour so
   "Direto do forno" shows fresh items.
2. **Live orders** — shifts non-terminal orders (new, confirmed, preparing,
   ready) to appear recent, preserving their relative event progression.
3. **KDS tickets** — adjusts completed_at for tickets linked to refreshed
   orders.

Uses queryset.update() throughout to bypass auto_now / auto_now_add guards
and Move's immutability check.

Usage:
    python manage.py refresh_oven
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Refresh time-sensitive seed data (production moves, live orders, KDS) for dev."

    def handle(self, *args, **options):
        now = timezone.now()
        self._refresh_production_moves(now)
        self._refresh_live_orders(now)

    def _refresh_production_moves(self, now):
        """Spread production Move timestamps across the last hour."""
        from shopman.stockman.models import Move

        moves = list(
            Move.objects.filter(
                reason__istartswith="Recebido de produção",
                delta__gt=0,
                quant__position__is_saleable=True,
            )
            .order_by("-timestamp")
            .values_list("pk", flat=True)[:10]
        )

        if not moves:
            self.stdout.write("  Nenhum Move de produção encontrado.")
            return

        for i, pk in enumerate(moves):
            offset = timedelta(minutes=5 + i * 10)
            Move.objects.filter(pk=pk).update(timestamp=now - offset)

        self.stdout.write(f"  Forno: {len(moves)} Moves atualizados.")

    def _refresh_live_orders(self, now):
        """Shift non-terminal orders to appear recent.

        Mirrors the seed's live_specs offsets:
        - preparing: 5–15 min ago
        - confirmed: 2–5 min ago
        - new: 1–4 min ago
        - ready: 1 min ago
        """
        from shopman.orderman.models import Order, OrderEvent

        live_orders = list(
            Order.objects.exclude(
                status__in=["completed", "cancelled", "returned"],
            ).order_by("status", "created_at")
        )

        if not live_orders:
            self.stdout.write("  Nenhum pedido live encontrado.")
            return

        offsets = {
            "preparing": (5, 15),
            "confirmed": (2, 5),
            "new": (1, 4),
            "ready": (1, 1),
        }

        for order in live_orders:
            lo, hi = offsets.get(order.status, (1, 5))
            minutes_ago = random.randint(lo, hi)
            new_order_time = now - timedelta(minutes=minutes_ago)

            # How much to shift all timestamps
            delta = new_order_time - order.created_at

            # Shift order timestamp
            Order.objects.filter(pk=order.pk).update(
                created_at=new_order_time,
            )

            # Shift all events for this order, preserving relative progression
            events = list(
                OrderEvent.objects.filter(order=order).values_list("pk", "created_at")
            )
            for evt_pk, evt_time in events:
                OrderEvent.objects.filter(pk=evt_pk).update(
                    created_at=evt_time + delta,
                )

            # Shift KDS ticket completed_at if present
            try:
                from shopman.shop.models import KDSTicket

                tickets = list(
                    KDSTicket.objects.filter(order=order, completed_at__isnull=False)
                    .values_list("pk", "completed_at")
                )
                for tkt_pk, tkt_time in tickets:
                    KDSTicket.objects.filter(pk=tkt_pk).update(
                        completed_at=tkt_time + delta,
                    )
            except Exception:
                pass

        self.stdout.write(f"  Pedidos: {len(live_orders)} orders atualizados.")
