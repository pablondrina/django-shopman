from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text()


def test_kds_realtime_region_has_aria_live_and_audio_labels():
    html = _read("shopman/backstage/templates/kds/display.html")

    assert 'aria-live="polite"' in html
    assert "aria-relevant" in html
    assert "Som ativo" in html
    assert "Som desativado" in html


def test_order_production_dependency_uses_progressbar():
    html = _read("shopman/backstage/templates/pedidos/partials/detail.html")

    assert "Aguardando produção" in html
    assert 'role="progressbar"' in html
    assert 'aria-valuenow="{{ wo.progress_pct }}"' in html


def test_production_shortage_modal_is_accessible():
    html = _read("shopman/backstage/templates/gestor/producao/partials/order_shortage.html")

    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="order-short-title"' in html


def test_closing_reconciliation_has_textual_discrepancy_state():
    html = _read("shopman/backstage/templates/gestor/fechamento/index.html")

    assert "Discrepâncias detectadas" in html
    assert "Produção do dia" in html
    assert "déficit" in html


def test_accessibility_guide_documents_manual_audit():
    doc = _read("docs/guides/backstage-accessibility.md")

    assert "axe DevTools" in doc
    assert "VoiceOver" in doc
    assert "Touch targets" in doc
