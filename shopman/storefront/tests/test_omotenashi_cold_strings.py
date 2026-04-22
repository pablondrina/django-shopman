"""Anti-regression tests: cold states must always have recovery paths.

Rule: a moment of friction or failure ("PIX expirado", "cancelado", "Indisponível")
must be accompanied by a clear next step. These tests guard against recovery paths
being accidentally removed during template edits.

Complements test_omotenashi_regression.py (which checks cold strings are *absent*).
This file checks cold *states* have *warm exits*.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEMPLATES_ROOT = Path(__file__).resolve().parents[1] / "templates" / "storefront"


def _read(rel: str) -> str:
    return (TEMPLATES_ROOT / rel).read_text(encoding="utf-8")


# ── 1. "Indisponível" must stay inside badge-neutral ──────────────────────────


def test_unavailable_badge_has_badge_class():
    """'Indisponível' in availability_badge.html must use badge-neutral class."""
    content = _read("components/availability_badge.html")
    for line in content.splitlines():
        stripped = line.strip()
        if "Indisponível" not in stripped:
            continue
        # Skip comment lines ({% comment %}, {# ... #}, or HTML <!-- -->)
        if stripped.startswith(("{#", "<!--", "unavailable", "available")):
            continue
        assert "badge-neutral" in line, (
            f"'Indisponível' without badge-neutral class: {line!r}"
        )


def test_unavailable_string_absent_outside_badge_component():
    """'Indisponível' must only appear in the badge component, never bare in other templates."""
    violations: list[str] = []
    for path in TEMPLATES_ROOT.rglob("*.html"):
        if "availability_badge" in str(path):
            continue
        if "Indisponível" in path.read_text(encoding="utf-8"):
            violations.append(str(path.relative_to(TEMPLATES_ROOT)))
    assert not violations, (
        f"Bare 'Indisponível' found outside badge component: {violations}. "
        "Use availability_badge.html or omotenashi copy instead."
    )


# ── 2. PIX expiry must always pair with a regenerate button ───────────────────


def test_pix_expired_display_is_transient_alpine_state():
    """In _payment_pix.html, 'PIX expirado' must be inside x-show (visible only when timer hits zero)."""
    content = _read("_payment_pix.html")
    assert "PIX expirado" in content, "_payment_pix.html must have a PIX expiry state"
    idx = content.index("PIX expirado")
    # Within 300 chars before the string there must be an x-show
    window = content[max(0, idx - 300) : idx + 100]
    assert "x-show" in window, (
        "'PIX expirado' in _payment_pix.html must be inside an x-show container "
        "(transient — not always visible)."
    )


def test_payment_status_expired_has_omotenashi_copy_and_regenerate():
    """payment_status.html must pair PIX expiry copy with a regenerate button."""
    content = _read("partials/payment_status.html")
    assert "PAYMENT_PIX_EXPIRED" in content, (
        "payment_status.html expired state must use PAYMENT_PIX_EXPIRED omotenashi copy"
    )
    assert "Gerar novo PIX" in content, (
        "payment_status.html expired state must have a 'Gerar novo PIX' button"
    )
    # Regenerate button must appear after the expired block (not elsewhere)
    idx_expired = content.index("is_expired")
    idx_btn = content.index("Gerar novo PIX")
    assert idx_btn > idx_expired, "Regenerate button must appear inside/after the expired block"


# ── 3. Cancelled state must never be a dead end ───────────────────────────────


def test_cancelled_order_has_navigation_recovery():
    """'Pedido cancelado' must be accompanied by a link to view order details."""
    content = _read("partials/payment_status.html")
    lower = content.lower()
    assert "cancelado" in lower, "Cancelled state expected in payment_status.html"
    idx = lower.index("cancelado")
    # Within 400 chars after, there must be a recovery navigation
    window = content[idx : idx + 400]
    has_recovery = (
        "order_tracking" in window
        or "Ver detalhes" in window
        or "Ver pedido" in window
    )
    assert has_recovery, (
        "'Pedido cancelado' must be followed by a recovery link "
        "(order_tracking, 'Ver detalhes', or 'Ver pedido') within 400 chars."
    )


def test_cancel_refused_has_whatsapp_recovery():
    """order_tracking.html cancel-refused block must offer WhatsApp as recovery path."""
    content = _read("order_tracking.html")
    assert "cancel_refused_message" in content, (
        "order_tracking.html must handle cancel_refused_message"
    )
    idx = content.index("cancel_refused_message")
    block = content[idx : idx + 600]
    assert "whatsapp_url" in block, (
        "Cancel-refused block must offer WhatsApp contact as recovery path"
    )


def test_kintsugi_cancel_refused_copy_defined():
    """KINTSUGI_CANCEL_REFUSED must be defined in omotenashi defaults."""
    from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS

    assert "KINTSUGI_CANCEL_REFUSED" in OMOTENASHI_DEFAULTS, (
        "KINTSUGI_CANCEL_REFUSED copy key must be defined so cancelled orders get warm copy"
    )
