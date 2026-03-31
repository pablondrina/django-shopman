"""Remove expired D-1 stock from position 'ontem'."""

from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from shopman.stocking.models import Move, Quant
from shopman.stocking.models.position import Position
from shopman.stocking.services.movements import StockMovements


class Command(BaseCommand):
    help = "Remove D-1 stock older than 1 day from position 'ontem' (register as loss)."

    def handle(self, *args, **options):
        ontem_pos = Position.objects.filter(ref="ontem").first()
        if not ontem_pos:
            self.stdout.write("Posição 'ontem' não existe. Nada a fazer.")
            return

        quants = Quant.objects.filter(position=ontem_pos, _quantity__gt=0)
        if not quants.exists():
            self.stdout.write("Sem estoque D-1. Nada a fazer.")
            return

        threshold = date.today() - timedelta(days=1)
        removed_count = 0

        for quant in quants:
            last_d1_move = (
                Move.objects.filter(quant=quant, reason__startswith="d1:")
                .order_by("-timestamp")
                .first()
            )
            if not last_d1_move:
                continue

            if last_d1_move.timestamp.date() >= threshold:
                continue

            qty = quant._quantity
            if qty <= 0:
                continue

            StockMovements.issue(
                quantity=qty,
                quant=quant,
                reason=f"perda_d1_vencido:{date.today()}",
            )
            self.stdout.write(f"Removido: {quant.sku} x{qty}")
            removed_count += 1

        if removed_count == 0:
            self.stdout.write("Nenhum D-1 vencido encontrado.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Cleanup concluído: {removed_count} item(ns) removido(s)."))
