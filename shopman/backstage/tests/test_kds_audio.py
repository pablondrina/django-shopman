from pathlib import Path


def test_kds_audio_state_uses_local_storage_and_alt_s_shortcut():
    source = Path("shopman/backstage/templates/runtime/kds_station/index.html").read_text()

    assert "localStorage.getItem(\"kds_sound_\"" in source
    assert "localStorage.setItem(\"kds_sound_\"" in source
    assert "@keydown.window.alt.s" in source
    # A real beep, not a stub: the new-ticket cue uses the Web Audio API.
    assert "AudioContext" in source
    assert "$store.kdsSound.observe" in (
        Path("shopman/backstage/templates/runtime/kds_station/partials/cards.html").read_text()
    )


def test_kds_station_listens_to_kds_sse_with_polling_fallback():
    source = Path("shopman/backstage/templates/runtime/kds_station/index.html").read_text()

    assert "kind='kds'" in source
    assert "sse:backstage-kds-update" in source
    assert "every 15s" in source
    assert 'aria-live="polite"' in source
