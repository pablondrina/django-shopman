"""Generate the production contract mirror consumed by the production-nuxt surface.

The contract's single source of truth is the projection dataclasses in
``shopman.backstage.projections.production``. The fournil app used to
hand-sync those shapes in TypeScript — a fragile manual mirror. This command
renders them into a generated TypeScript module, so the surface imports (and
narrows) them instead of re-declaring them.

A drift test (``test_production_schema_export``) regenerates the file
in-memory and compares it to disk, failing loudly when the two diverge. Run::

    python manage.py export_production_schema

after touching the projection dataclasses.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from shopman.backstage.contracts import render_contract_module, run_contract_export
from shopman.backstage.projections.production import (
    BaseRecipeOptionProjection,
    BaseRecipeUsageProjection,
    ForecastRowProjection,
    MiseEnPlaceBreakdownProjection,
    MiseEnPlaceLineProjection,
    OrderCommitmentProjection,
    PositionOptionProjection,
    ProductionBoardProjection,
    ProductionCountsProjection,
    ProductionForecastProjection,
    ProductionKDSCardProjection,
    ProductionKDSProjection,
    ProductionMatrixGroupProjection,
    ProductionMatrixGroupRowProjection,
    ProductionMatrixRowProjection,
    ProductionMiseEnPlaceProjection,
    ProductionSuggestionProjection,
    ProductionSurfaceAccess,
    ProductionWeighingIngredientProjection,
    ProductionWeighingProjection,
    ProductionWeighingTicketProjection,
    RecipeOptionProjection,
    WorkOrderCardProjection,
)

#: Generated artifact, relative to the repository root (``BASE_DIR``).
OUTPUT_RELATIVE_PATH = Path("surfaces/production-nuxt/app/generated/productionContract.ts")

#: Every dataclass exported to the surface, dependencies first.
CONTRACT_DATACLASSES = (
    OrderCommitmentProjection,
    BaseRecipeUsageProjection,
    WorkOrderCardProjection,
    ProductionCountsProjection,
    RecipeOptionProjection,
    BaseRecipeOptionProjection,
    PositionOptionProjection,
    ProductionSuggestionProjection,
    ProductionMatrixRowProjection,
    ProductionMatrixGroupRowProjection,
    ProductionMatrixGroupProjection,
    ProductionSurfaceAccess,
    ProductionBoardProjection,
    ProductionKDSCardProjection,
    ProductionKDSProjection,
    ForecastRowProjection,
    ProductionForecastProjection,
    MiseEnPlaceBreakdownProjection,
    MiseEnPlaceLineProjection,
    ProductionMiseEnPlaceProjection,
    ProductionWeighingIngredientProjection,
    ProductionWeighingTicketProjection,
    ProductionWeighingProjection,
)


def output_path() -> Path:
    return Path(settings.BASE_DIR) / OUTPUT_RELATIVE_PATH


def render_production_contract_ts() -> str:
    """Render the generated TypeScript contract mirror (deterministic)."""
    return render_contract_module(
        source="shopman/backstage/projections/production.py",
        command="export_production_schema",
        dataclasses=CONTRACT_DATACLASSES,
    )


class Command(BaseCommand):
    help = "Generate the production contract mirror (TypeScript) from the projections."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero if the generated file is stale (do not write).",
        )

    def handle(self, *args, **options) -> None:
        run_contract_export(
            self,
            relative_path=OUTPUT_RELATIVE_PATH,
            rendered=render_production_contract_ts(),
            check=bool(options.get("check")),
        )
