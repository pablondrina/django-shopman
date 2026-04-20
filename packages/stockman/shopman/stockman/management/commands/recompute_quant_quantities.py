"""
Management command: recompute_quant_quantities

Audits and optionally corrects divergence between Quant._quantity (cache)
and Σ(moves.delta) (source of truth).

Usage:
    python manage.py recompute_quant_quantities --dry-run
    python manage.py recompute_quant_quantities --apply
    python manage.py recompute_quant_quantities --dry-run --sku croissant
    python manage.py recompute_quant_quantities --apply  --sku croissant

Exit codes:
    0  — no divergence found (dry-run) or all divergences corrected (apply)
    1  — divergences detected in dry-run (nothing written)
"""

import logging
import sys

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db.models.functions import Coalesce

from shopman.stockman.models.quant import Quant

logger = logging.getLogger('shopman.stockman')


class Command(BaseCommand):
    help = 'Audita e corrige divergências em Quant._quantity vs Σ(moves.delta)'

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument(
            '--dry-run',
            action='store_true',
            help='Reporta divergências sem corrigir (exit 1 se há divergência)',
        )
        mode.add_argument(
            '--apply',
            action='store_true',
            help='Aplica recalculate() nos quants divergentes (exit 0)',
        )
        parser.add_argument(
            '--sku',
            metavar='SKU',
            help='Limita verificação a um SKU específico',
        )

    def handle(self, *args, **options):
        qs = Quant.objects.prefetch_related('moves').order_by('pk')
        if options.get('sku'):
            qs = qs.filter(sku=options['sku'])

        divergent = self._find_divergent(qs)

        if not divergent:
            self.stdout.write(self.style.SUCCESS('Nenhuma divergência encontrada.'))
            return  # exit 0

        self._print_table(divergent)

        if options['dry_run']:
            self.stderr.write(
                self.style.ERROR(f'{len(divergent)} divergência(s) encontrada(s). Execute --apply para corrigir.')
            )
            logger.warning(
                "quant.divergence_detected_dry_run",
                extra={"count": len(divergent), "sku_filter": options.get('sku')},
            )
            sys.exit(1)

        # --apply
        fixed = 0
        for quant, computed in divergent:
            quant.recalculate()
            fixed += 1

        self.stdout.write(
            self.style.SUCCESS(f'{fixed} quant(s) corrigido(s).')
        )

    def _find_divergent(self, qs):
        """Return list of (quant, computed_qty) for quants with cache mismatch."""
        from decimal import Decimal

        divergent = []
        for quant in qs:
            computed = quant.moves.aggregate(
                t=Coalesce(Sum('delta'), Decimal('0'))
            )['t']
            if computed != quant._quantity:
                divergent.append((quant, computed))
        return divergent

    def _print_table(self, divergent):
        header = f"{'pk':>8}  {'sku':<30}  {'position':<12}  {'current':>12}  {'computed':>12}  {'delta':>12}"
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for quant, computed in divergent:
            delta = computed - quant._quantity
            pos = str(quant.position_id or '-')
            self.stdout.write(
                f"{quant.pk:>8}  {quant.sku:<30}  {pos:<12}  "
                f"{quant._quantity:>12}  {computed:>12}  {delta:>+12}"
            )
