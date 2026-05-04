"""Backstage UI guardrails derived from the surface design filter."""

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEMPLATES = ROOT / "templates"
CSS_SOURCE = ROOT.parents[1] / "static" / "src" / "style-gestor.css"


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


def test_backstage_shell_keeps_accessible_viewport_and_canonical_css():
    base = (TEMPLATES / "gestor" / "base.html").read_text(encoding="utf-8")
    css = CSS_SOURCE.read_text(encoding="utf-8")

    assert "maximum-scale" not in base
    assert "output-gestor.css" in base
    assert 'class="h-full md:flex"' in base
    assert "md:w-[calc(100vw-3.5rem)]" in base
    assert "overflow-x: clip" in css
    assert "@media (max-width: 767px)" in css
    assert "font-size: 16px" in css
    assert ".htmx-indicator { display: none;" in css


def test_backstage_design_tokens_expose_canonical_components():
    css = CSS_SOURCE.read_text(encoding="utf-8")

    for token in (
        ".icon-sm",
        ".icon-md",
        ".icon-lg",
        ".icon-display",
        ".btn-ghost",
        ".btn-quiet",
        ".surface-modal",
        ".empty-state",
        ".field-label",
        ".metric-value",
        ".count-badge",
        ".order-timer",
        ".timer-late",
        ".segmented-action",
    ):
        assert token in css

    assert "placeholder:text-on-surface/70" in css
    assert "placeholder:text-on-surface/40" not in css
    assert ".material-symbols-rounded.icon-sm { font-size: 1rem; }" in css
    assert ".order-timer .material-symbols-rounded" in css


def test_backstage_templates_avoid_micro_type_and_loose_dashes():
    for name, raw_source in _template_sources().items():
        source = _visible_source(raw_source)
        assert "text-[8px]" not in source, name
        assert "text-[9px]" not in source, name
        assert "text-[10px]" not in source, name
        assert "text-[0.6875rem]" not in source, name
        assert "&mdash;" not in source, name
        assert " — " not in source, name


def test_backstage_pos_uses_composition_components_instead_of_local_one_offs():
    pos = (TEMPLATES / "pos" / "index.html").read_text(encoding="utf-8")

    assert "segmented-action" in pos
    assert "segmented-action--active" in pos
    assert "btn-quiet flex-1" in pos
    assert "surface-modal max-w-sm" in pos
    assert "badge-warning leading-none" in pos
    assert "rounded-2xl" not in pos


def test_backstage_empty_states_and_icons_use_canonical_scale():
    sources = _template_sources()

    assert 'component "unfold/components/table.html"' in sources["admin_console/kds/partials/tickets.html"]
    assert 'component "unfold/components/table.html"' in sources["admin_console/closing/index.html"]
    assert 'component "unfold/components/table.html"' in sources["admin_console/kds/index.html"]
    assert "icon-display" in sources["pos/index.html"]
    assert "icon-md" in sources["gestor/base.html"]


def test_backstage_order_queue_is_admin_unfold_surface():
    index = (TEMPLATES / "admin_console" / "orders" / "index.html").read_text(encoding="utf-8")
    detail = (TEMPLATES / "admin_console" / "orders" / "detail.html").read_text(encoding="utf-8")
    actions = (TEMPLATES / "admin_console" / "orders" / "cells" / "actions.html").read_text(encoding="utf-8")
    admin_console = Path("shopman/backstage/admin_console/orders.py").read_text(encoding="utf-8")

    assert '{% extends "admin/base.html" %}' in index
    assert 'include "unfold/helpers/tab_list.html"' in index
    assert 'include "admin_console/orders/partials/sections.html"' in index
    assert 'component "unfold/components/table.html"' in detail
    assert 'include "unfold/helpers/field.html"' in detail
    assert 'component "unfold/components/button.html"' in actions
    assert "build_two_zone_queue" in admin_console
    assert "_order_sections" in admin_console
    assert "Entrada" in admin_console
    assert "Preparo" in admin_console
    assert "Saida" in admin_console
    assert "order_service.confirm_order" in admin_console
    assert "order_service.advance_order" in admin_console
    assert "order_service.reject_order" in admin_console


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
    assert "set_planned" in admin_console
    assert "production_order_sections" in admin_console
    assert "_details_table" in admin_console
    assert ">Sugerido<" not in production
    assert "Salvar planejado" in admin_console
    assert "quantity_display" in admin_console
    assert "per_unit_display" in admin_console
    assert "adjustOpen" in cells
    assert "admin_console/unfold/modal.html" in cells
    assert "surface-modal max-w-sm" not in production
    assert "Planejar manualmente" not in production
    assert "Planejar sugerido" not in production
