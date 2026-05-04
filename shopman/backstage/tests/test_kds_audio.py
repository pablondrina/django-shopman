from pathlib import Path


def test_kds_audio_state_uses_local_storage_and_alt_s_shortcut():
    source = Path("shopman/backstage/templates/admin_console/kds/partials/kds_js.html").read_text()

    assert "localStorage.getItem('kds_sound_'" in source
    assert "localStorage.setItem('kds_sound_'" in source
    assert "e.altKey && (e.key === 's' || e.key === 'S')" in source
    assert "this.playSound('new')" in source


def test_kds_display_listens_to_kds_sse_with_polling_fallback():
    source = Path("shopman/backstage/templates/admin_console/kds/display.html").read_text()

    assert "kind='kds'" in source
    assert "sse:backstage-kds-update" in source
    assert "every 30s" in source
    assert 'aria-live="polite"' in source
