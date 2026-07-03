"""
Management command: suggest production quantities based on demand history.

Delegates to the orchestration helper ``production.suggest_for()`` so the CLI
sees exactly the same suggestion as the planning surfaces: season, high-demand
multiplier and safety margin come from ``ProductionConfig``
(``Shop.defaults["production"]``).

Usage:
    python manage.py suggest_production                # suggestions for tomorrow
    python manage.py suggest_production --date 2026-03-26
    python manage.py suggest_production --skus PAO-FRANCES CROISSANT
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Suggest production quantities based on demand history"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Target date (YYYY-MM-DD). Defaults to tomorrow.",
        )
        parser.add_argument(
            "--skus",
            nargs="*",
            default=None,
            help="Filter by product SKUs (output_skus). If omitted, all active recipes.",
        )

    def handle(self, *args, **options):
        from shopman.shop.services.production import suggest_for

        target_date = self._parse_date(options["date"])
        output_skus = options["skus"]

        self.stdout.write(f"\nSugestão de produção para {target_date}")
        self.stdout.write("=" * 60)

        suggestions = suggest_for(target_date, output_skus=output_skus)

        if not suggestions:
            self.stdout.write(
                self.style.WARNING(
                    "\nNenhuma sugestão gerada.\n"
                    "Possíveis causas:\n"
                    "  - CRAFTSMAN['DEMAND_BACKEND'] não configurado\n"
                    "  - Nenhuma receita ativa encontrada\n"
                    "  - Sem histórico de demanda suficiente"
                )
            )
            return

        confidence_colors = {
            "high": self.style.SUCCESS,
            "medium": self.style.WARNING,
            "low": self.style.ERROR,
        }

        for s in suggestions:
            basis = s.basis
            avg = basis.get("avg_demand", Decimal("0"))
            committed = basis.get("committed", Decimal("0"))
            safety = basis.get("safety_pct", Decimal("0"))
            sample = basis.get("sample_size", 0)
            confidence = basis.get("confidence", "low")
            waste_rate = basis.get("waste_rate")
            high_demand_applied = basis.get("high_demand_applied", False)
            season = basis.get("season")

            color = confidence_colors.get(confidence, lambda x: x)
            confidence_label = color(f"{confidence.upper()}")

            waste_str = f" | waste: {waste_rate:.0%}" if waste_rate else ""
            season_str = f" | estação: {season}" if season else ""
            hd_str = " | alta demanda ✓" if high_demand_applied else ""

            self.stdout.write(
                f"\n  {s.recipe.name} ({s.recipe.output_sku}):"
                f"\n    Produzir: {s.quantity} unidades"
                f"\n    Confiança: {confidence_label}{season_str}{waste_str}{hd_str}"
                f"\n    Demanda média: {avg:.1f} (amostra: {sample} dias)"
                f"\n    Comprometido: {committed}"
                f"\n    Margem segurança: {safety:.0%}"
            )

        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write(
            self.style.SUCCESS(f"\nTotal: {len(suggestions)} receitas sugeridas\n")
        )

    def _parse_date(self, date_str):
        if date_str is None:
            return date.today() + timedelta(days=1)
        return date.fromisoformat(date_str)
