from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text()


# O KDS e o console de pedidos viraram apps Nuxt dedicados (a11y via vitest +
# verificação ao vivo); seus checks de template Django foram removidos (Fase 2).


def test_production_shortage_modal_is_accessible():
    # O modal de order-shortage migrou para o Fournil junto com o plan (split
    # canônico WP-PE4); no Admin resta o de insumos (finish/quick_finish),
    # que delega ao wrapper aprovado — os atributos ARIA vivem nele.
    partial = _read("shopman/backstage/templates/admin_console/production/partials/material_shortage.html")

    assert 'include "admin_console/unfold/modal.html"' in partial

    wrapper = _read("shopman/backstage/templates/admin_console/unfold/modal.html")

    assert 'role="dialog"' in wrapper
    assert 'aria-modal="true"' in wrapper


def test_closing_reconciliation_has_textual_discrepancy_state():
    html = _read("shopman/backstage/templates/admin_console/closing/index.html")

    assert "Discrepancias detectadas" in html
    assert "Producao do dia" in html
    assert "day_closing_reconciliation_table" in html


def test_accessibility_guide_documents_manual_audit():
    doc = _read("docs/guides/backstage-accessibility.md")

    assert "axe DevTools" in doc
    assert "VoiceOver" in doc
    assert "Touch targets" in doc
