"""
Management command: suggest production quantities based on demand history.

Uses CraftService.suggest() with the configured DemandBackend to generate
recommendations for what to produce on a given date.

Usage:
    python manage.py suggest_production                # suggestions for tomorrow
    python manage.py suggest_production --date 2026-03-26
    python manage.py suggest_production --skus PAO-FRANCES CROISSANT
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand


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
            help="Filter by product SKUs (output_refs). If omitted, all active recipes.",
        )

    def handle(self, *args, **options):
        from shopman.crafting.service import CraftService as craft

        target_date = self._parse_date(options["date"])
        output_refs = options["skus"]

        self.stdout.write(f"\nSugestão de produção para {target_date}")
        self.stdout.write("=" * 60)

        suggestions = craft.suggest(date=target_date, output_refs=output_refs)

        if not suggestions:
            self.stdout.write(
                self.style.WARNING(
                    "\nNenhuma sugestão gerada.\n"
                    "Possíveis causas:\n"
                    "  - CRAFTING['DEMAND_BACKEND'] não configurado\n"
                    "  - Nenhuma receita ativa encontrada\n"
                    "  - Sem histórico de demanda suficiente"
                )
            )
            return

        for s in suggestions:
            basis = s.basis
            avg = basis.get("avg_demand", Decimal("0"))
            committed = basis.get("committed", Decimal("0"))
            safety = basis.get("safety_pct", Decimal("0"))
            sample = basis.get("sample_size", 0)

            self.stdout.write(
                f"\n  {s.recipe.name} ({s.recipe.output_ref}):"
                f"\n    Produzir: {s.quantity} unidades"
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
