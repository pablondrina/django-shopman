from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text()


# O KDS e o console de pedidos viraram apps Nuxt dedicados (a11y via vitest +
# verificação ao vivo); seus checks de template Django foram removidos (Fase 2).
# O console de produção (e o wrapper aprovado de modal, que só ele usava) saiu
# no WP-ADM-7d: os modais e a a11y das telas de produção são do Fournil
# (surfaces/production-nuxt), testados na suite do app Nuxt.


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
