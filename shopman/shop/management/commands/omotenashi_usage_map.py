"""Regenera o snapshot do mapa chave↔tela da copy omotenashi.

Rode após adicionar/mover consumo de copy (`resolve_copy`/`copy.title`):

    .venv/bin/python manage.py omotenashi_usage_map

O teste de deriva (shopman/shop/tests) falha quando o snapshot está velho.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.shop.omotenashi.usage import REPO_ROOT, render_usage_map, scan_usages


class Command(BaseCommand):
    help = "Regenera shopman/shop/omotenashi/usage_map.py a partir do código."

    def handle(self, *args, **options):
        usages = scan_usages()
        target = REPO_ROOT / "shopman/shop/omotenashi/usage_map.py"
        target.write_text(render_usage_map(usages), encoding="utf-8")
        mapped = sum(1 for refs in usages.values() if refs)
        self.stdout.write(
            self.style.SUCCESS(
                f"usage_map.py regenerado: {mapped}/{len(usages)} chaves com uso mapeado."
            )
        )
