"""Backstage UI guardrails derived from the surface design filter."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
TEMPLATES = ROOT / "templates"


def _template_sources() -> dict[str, str]:
    return {
        str(path.relative_to(TEMPLATES)): path.read_text(encoding="utf-8")
        for path in TEMPLATES.rglob("*.html")
    }


def _visible_source(source: str) -> str:
    source = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", source, flags=re.S)
    source = re.sub(r"{#.*?#}", "", source, flags=re.S)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"//.*", "", source)
    return source


# The legacy operator shell (gestor/base.html) was retired with the production
# app cutover (OPERATOR-APPS-PLAN Fase 4) — operator surfaces are dedicated Nuxt
# apps, and the root Tailwind pipeline (static/src/style-gestor.css) went with
# them: no Admin template nor UNFOLD["STYLES"] ever linked its output.


def test_backstage_templates_avoid_micro_type_and_loose_dashes():
    for name, raw_source in _template_sources().items():
        source = _visible_source(raw_source)
        assert "text-[8px]" not in source, name
        assert "text-[9px]" not in source, name
        assert "text-[10px]" not in source, name
        assert "text-[0.6875rem]" not in source, name
        assert "&mdash;" not in source, name
        assert " — " not in source, name


# O POS-HTMX (templates/pos/) saiu (SURFACE-CONVERGENCE-PLAN WP1); o POS é o Nuxt
# (surfaces/pos-nuxt), com componentes/escala próprios testados lá (vitest).


def test_backstage_empty_states_and_icons_use_canonical_scale():
    sources = _template_sources()

    assert 'component "unfold/components/table.html"' in sources["admin_console/closing/index.html"]


# A fila de pedidos virou app Nuxt dedicado (Gestor); deixou de ser superfície
# Admin/Unfold, então o guardrail Unfold do console de pedidos foi removido (Fase 2).


def test_backstage_production_uses_high_volume_matrix_surface():
    production = (TEMPLATES / "admin_console" / "production" / "index.html").read_text(encoding="utf-8")
    admin_console = Path("shopman/backstage/admin_console/production.py").read_text(encoding="utf-8")
    cells = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (TEMPLATES / "admin_console" / "production" / "cells").glob("*.html")
    )

    assert "Produção do dia" in production
    assert "Mapa de produção" not in production
    assert "Matriz de produção" not in production
    assert "filtersOpen" in production
    assert "production_filter_summary" in production
    assert "production_order_sections" in production
    assert "production_matrix_table" in production
    assert "matrix_groups" in admin_console
    assert "Ficha-base" in admin_console
    assert "base_recipe" in admin_console
    assert "production_order_sections" in admin_console
    assert "_details_table" in admin_console
    assert ">Sugerido<" not in production
    assert "quantity_display" in admin_console
    assert "per_unit_display" in admin_console
    # Split canônico (WP-PE4): a matriz do Admin é LEITURA — planejar/ajustar/
    # iniciar/concluir vive no Fournil. Nenhuma escrita de produção no Admin:
    # os cells apresentam estado, sem modais de ação.
    assert "admin_console/unfold/modal.html" not in cells
    planning = (TEMPLATES / "admin_console" / "production" / "planning.html").read_text(encoding="utf-8")
    planning_cell = (
        TEMPLATES / "admin_console" / "production" / "cells" / "planning_planned.html"
    ).read_text(encoding="utf-8")
    assert "set_planned" not in admin_console
    assert "Salvar planejado" not in admin_console
    assert "adjustOpen" not in planning_cell
    assert "modal" not in planning_cell
    assert "production_fournil_planning_url" in planning
    assert "surface-modal max-w-sm" not in production
    assert "Planejar manualmente" not in production
    assert "Planejar sugerido" not in production
