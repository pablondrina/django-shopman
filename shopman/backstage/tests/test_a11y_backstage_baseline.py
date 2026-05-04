from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text()


def test_kds_realtime_region_has_aria_live_and_audio_labels():
    html = _read("shopman/backstage/templates/admin_console/kds/display.html")

    assert 'aria-live="polite"' in html
    assert "aria-relevant" in html
    assert "Som ativo" in html
    assert "Som desativado" in html


def test_order_production_dependency_uses_progressbar():
    controller = _read("shopman/backstage/admin_console/orders.py")

    assert "build_operator_order" in controller
    assert "awaiting_work_orders" in controller
    assert "progress_pct" in controller


def test_production_shortage_modal_is_accessible():
    html = _read("shopman/backstage/templates/gestor/producao/partials/order_shortage.html")

    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="order-short-title"' in html


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
