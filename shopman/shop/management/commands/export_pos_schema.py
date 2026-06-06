"""Generate the POS sale-intent contract mirror consumed by the Nuxt surface.

The contract's single source of truth lives in the orchestrator
(``shopman.shop.services.pos_intent``). The Nuxt PDV used to hand-sync the
intent version and the payment/receipt enums in TypeScript — a fragile manual
mirror. This command renders those from the Python source into a generated
TypeScript module, so the surface imports them instead of re-declaring them.

A drift test (``test_pos_schema_export``) regenerates the file in-memory and
compares it to disk, failing loudly when the two diverge. Run::

    python manage.py export_pos_schema

after touching the contract in ``pos_intent.py``.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from shopman.shop.services.pos_intent import (
    POS_SALE_INTENT_PAYMENT_COLLECTIONS,
    POS_SALE_INTENT_PAYMENT_METHODS,
    POS_SALE_INTENT_RECEIPT_MODES,
    POS_SALE_INTENT_VERSION,
)

#: Generated artifact, relative to the repository root (``BASE_DIR``).
OUTPUT_RELATIVE_PATH = Path("surfaces/pos-uithing-nuxt/app/generated/posContract.ts")


def output_path() -> Path:
    return Path(settings.BASE_DIR) / OUTPUT_RELATIVE_PATH


def _const_array(name: str, type_name: str, values: tuple[str, ...]) -> str:
    items = ", ".join(f'"{value}"' for value in values)
    return (
        f"export const {name} = [{items}] as const;\n"
        f"export type {type_name} = (typeof {name})[number];\n"
    )


def render_pos_contract_ts() -> str:
    """Render the generated TypeScript contract mirror (deterministic)."""
    blocks = [
        "// AUTO-GENERATED — do not edit by hand.",
        "// Source of truth: shopman/shop/services/pos_intent.py",
        "// Regenerate with: python manage.py export_pos_schema",
        "",
        f'export const POS_SALE_INTENT_VERSION = "{POS_SALE_INTENT_VERSION}";',
        "",
        _const_array("POS_PAYMENT_METHODS", "PosPaymentMethod", POS_SALE_INTENT_PAYMENT_METHODS),
        _const_array("POS_PAYMENT_COLLECTIONS", "PosPaymentCollection", POS_SALE_INTENT_PAYMENT_COLLECTIONS),
        _const_array("POS_RECEIPT_MODES", "PosReceiptMode", POS_SALE_INTENT_RECEIPT_MODES),
    ]
    return "\n".join(blocks).rstrip() + "\n"


class Command(BaseCommand):
    help = "Generate the POS sale-intent contract mirror (TypeScript) from pos_intent.py."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero if the generated file is stale (do not write).",
        )

    def handle(self, *args, **options) -> None:
        path = output_path()
        rendered = render_pos_contract_ts()
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if options.get("check"):
            if current != rendered:
                self.stderr.write(
                    self.style.ERROR(
                        f"{OUTPUT_RELATIVE_PATH} is stale. Run: python manage.py export_pos_schema"
                    )
                )
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS(f"{OUTPUT_RELATIVE_PATH} is up to date."))
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {OUTPUT_RELATIVE_PATH}"))
