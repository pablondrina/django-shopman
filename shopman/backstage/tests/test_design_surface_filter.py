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
# O console de produção seguiu o mesmo caminho no WP-ADM-7d: matriz, planejamento,
# painel, pesagem e relatórios vivem no Fournil (surfaces/production-nuxt), então
# o guardrail da matriz Admin foi removido junto com os templates.
