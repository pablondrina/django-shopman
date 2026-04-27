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
        ".segmented-action",
    ):
        assert token in css

    assert "placeholder:text-on-surface/70" in css
    assert "placeholder:text-on-surface/40" not in css


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

    assert "empty-state" in sources["kds/partials/ticket_list.html"]
    assert "empty-state" in sources["gestor/fechamento/index.html"]
    assert "empty-state" in sources["kds/index.html"]
    assert "icon-display" in sources["pos/index.html"]
    assert "icon-md" in sources["gestor/base.html"]


def test_backstage_order_queue_keeps_all_action_areas_visible_and_responsive():
    order_list = (TEMPLATES / "pedidos" / "partials" / "order_list.html").read_text(encoding="utf-8")
    card = (TEMPLATES / "pedidos" / "partials" / "card.html").read_text(encoding="utf-8")
    js = (TEMPLATES / "pedidos" / "partials" / "pedidos_js.html").read_text(encoding="utf-8")

    assert "Preparo" in order_list
    assert "queue.preparo" in order_list
    assert "queue.total_count" in order_list
    assert "writing-mode" not in order_list
    assert "overflow-y-auto p-3 space-y-4" in order_list
    assert "badge {{ o.status_color }}" in card
    assert "shrink-0 p-0" in card
    assert "var source = (e.detail && e.detail.elt) || e.target;" in js
    assert "if (source !== grid) return;" in js
