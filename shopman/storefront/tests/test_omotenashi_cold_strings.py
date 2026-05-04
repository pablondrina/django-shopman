"""Anti-regression tests: cold states must always have recovery paths.

Rule: a moment of friction or failure ("PIX expirado", "cancelado", "Indisponível")
must be accompanied by a clear next step. These tests guard against recovery paths
being accidentally removed during template edits.

Complements test_omotenashi_regression.py (which checks cold strings are *absent*).
This file checks cold *states* have *warm exits*.
"""

from __future__ import annotations

from pathlib import Path

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
    """In _payment_pix.html, PIX expiry copy (via omotenashi) must be inside x-show."""
    content = _read("_payment_pix.html")
    assert "PAYMENT_PIX_EXPIRED" in content, "_payment_pix.html must resolve PAYMENT_PIX_EXPIRED omotenashi key"
    assert "pix_expired.title" in content, "_payment_pix.html must render pix_expired.title"
    idx = content.index("pix_expired.title")
    window = content[max(0, idx - 300) : idx + 100]
    assert "x-show" in window, (
        "'pix_expired.title' in _payment_pix.html must be inside an x-show container "
        "(transient — not always visible)."
    )


def test_payment_status_expired_has_omotenashi_copy_and_regenerate():
    """payment_status.html must pair PIX expiry copy with a regenerate button."""
    content = _read("partials/payment_status.html")
    assert "PAYMENT_PIX_EXPIRED" in content, (
        "payment_status.html expired state must use PAYMENT_PIX_EXPIRED omotenashi copy"
    )
    assert "PAYMENT_PIX_REGENERATE_CTA" in content, (
        "payment_status.html expired state must have an Omotenashi-driven regenerate button"
    )
    # Regenerate button must appear after the expired block (not elsewhere)
    idx_expired = content.index("is_expired")
    idx_btn = content.index("PAYMENT_PIX_REGENERATE_CTA")
    assert idx_btn > idx_expired, "Regenerate button must appear inside/after the expired block"


# ── 3. Cancelled state must never be a dead end ───────────────────────────────


def test_cancelled_order_has_navigation_recovery():
    """'Pedido cancelado' must be accompanied by a link to view order details."""
    content = _read("partials/payment_status.html")
    assert "PAYMENT_CANCELLED" in content, "Cancelled state expected in payment_status.html"
    assert "PAYMENT_CANCELLED_DETAILS_CTA" in content, (
        "Cancelled state details CTA must be Omotenashi-driven"
    )
    idx = content.index("PAYMENT_CANCELLED")
    # Within 400 chars after, there must be a recovery navigation
    window = content[idx : idx + 400]
    has_recovery = "order_tracking" in window and "PAYMENT_CANCELLED_DETAILS_CTA" in window
    assert has_recovery, (
        "Cancelled payment state must be followed by an Omotenashi-driven recovery link."
    )


def test_payment_status_copy_is_omotenashi_driven():
    """Payment polling copy must stay editable through Omotenashi Admin."""
    content = _read("partials/payment_status.html")
    for key in (
        "PAYMENT_CONFIRMED",
        "TRACKING_ETA_PREFIX",
        "CONFIRMATION_TRACK_CTA",
        "PAYMENT_REDIRECTING_PREFIX",
        "PAYMENT_REDIRECTING_SUFFIX",
        "PAYMENT_PIX_EXPIRED",
        "PAYMENT_PIX_REGENERATE_CTA",
        "PAYMENT_VIEW_ORDER_CTA",
        "PAYMENT_CANCELLED",
        "PAYMENT_CANCELLED_DETAILS_CTA",
        "PAYMENT_WAITING",
        "PAYMENT_WAITING_LONG",
    ):
        assert key in content

    for literal in (
        "Previsão:",
        "Acompanhar pedido",
        "Redirecionando em",
        "Gerar novo PIX",
        "Ver pedido",
        "Pedido cancelado",
        "Ver detalhes",
    ):
        assert literal not in content


def test_payment_page_copy_is_omotenashi_driven():
    """Visible payment-page copy must stay editable through Omotenashi Admin."""
    content = _read("payment.html")
    for key in (
        "PAYMENT_PAGE_TITLE",
        "PAYMENT_PAGE_META_DESCRIPTION",
        "PAYMENT_ORDER_REF_LABEL",
        "PAYMENT_TOTAL_LABEL",
        "PAYMENT_DEV_CONFIRM_CTA",
        "PAYMENT_ERROR_TITLE",
        "PAYMENT_ERROR_MESSAGE",
        "PAYMENT_RETRY_CTA",
        "CONFIRMATION_TRACK_CTA",
    ):
        assert key in content

    for literal in (
        "Pagamento",
        "Conclua o pagamento do seu pedido",
        "Pedido {{ payment.order_ref }}",
        "Total",
        "[DEV] Simular pagamento confirmado",
        "Não conseguimos gerar o pagamento agora.",
        "Tentar novamente",
        "Acompanhar pedido",
    ):
        assert literal not in content


def test_cancel_refused_has_whatsapp_recovery():
    """order_tracking.html cancel-refused block must offer WhatsApp as recovery path."""
    content = _read("order_tracking.html")
    assert "cancel_refused" in content, (
        "order_tracking.html must handle cancel_refused state"
    )
    assert "KINTSUGI_CANCEL_REFUSED" in content, (
        "order_tracking.html cancel-refused block must use KINTSUGI_CANCEL_REFUSED omotenashi copy"
    )
    idx = content.index("cancel_refused")
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


def test_order_live_payment_flow_copy_is_omotenashi_driven():
    """Payment/tracking promise copy must be editable through Omotenashi Admin."""
    content = _read("partials/order_live.html")
    service_content = (
        Path(__file__).resolve().parents[2] / "shop" / "services" / "order_tracking.py"
    ).read_text(encoding="utf-8")
    for key in (
        "TRACKING_PAYMENT_PENDING",
        "TRACKING_PAYMENT_REQUESTED",
        "TRACKING_PAYMENT_CTA",
        "TRACKING_PAYMENT_TIME_LEFT",
        "TRACKING_PAYMENT_EXPIRED",
        "TRACKING_STEP_PAYMENT_CONFIRMED",
        "TRACKING_DELIVERY_WAITING_COURIER",
        "TRACKING_AUTO_CONFIRM_PREFIX",
    ):
        assert key in content or key in service_content

    for key in (
        "TRACKING_PROMISE_STALE",
        "TRACKING_PROMISE_UPDATED_NOW",
    ):
        assert key in content

    assert "Recebemos seu pedido." not in content
    assert "Aguardamos a confirmação do pagamento." not in content
    assert "O prazo para pagamento expirou." not in content
    assert "O pedido foi automaticamente cancelado." not in content
    assert "Pagamento confirmado." not in content


def test_order_tracking_payment_copy_defaults_defined():
    """Tracking payment copy keys must exist so Admin can override them."""
    from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS

    for key in (
        "TRACKING_STATUS_PAYMENT_PENDING",
        "TRACKING_STATUS_PAYMENT_EXPIRED",
        "TRACKING_STATUS_WAITING_STORE_CONFIRMATION",
        "TRACKING_PAYMENT_PENDING",
        "TRACKING_PAYMENT_REQUESTED",
        "TRACKING_PAYMENT_CTA",
        "TRACKING_PAYMENT_TIME_LEFT",
        "TRACKING_PAYMENT_EXPIRED",
        "TRACKING_PAYMENT_CONFIRMED",
        "TRACKING_DELIVERY_WAITING_COURIER",
        "TRACKING_ACTION_NONE",
        "TRACKING_ACTION_WAITING_COURIER",
        "TRACKING_ACTION_READY_PICKUP",
        "TRACKING_CARD_AUTHORIZED",
        "TRACKING_PROMISE_UPDATED_NOW",
        "TRACKING_PROMISE_LABEL_ACTION",
        "TRACKING_PROMISE_LABEL_NEXT",
        "TRACKING_PROMISE_LABEL_RECOVERY",
        "TRACKING_PROMISE_LABEL_ACTIVE_NOTIFICATION",
        "TRACKING_PROMISE_STALE",
        "TRACKING_PROMISE_PAYMENT_EXPIRED_NEXT",
        "TRACKING_PROMISE_RECOVERY_HELP",
        "TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_NEW",
        "TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_CONFIRMED",
        "TRACKING_PROMISE_PAYMENT_NEXT",
        "TRACKING_PROMISE_PAYMENT_RECOVERY",
        "TRACKING_PROMISE_PAYMENT_ACTIVE_NOTIFICATION",
        "TRACKING_PROMISE_AVAILABILITY_MESSAGE",
        "TRACKING_PROMISE_AVAILABILITY_NEXT",
        "TRACKING_PROMISE_AVAILABILITY_RECOVERY",
        "TRACKING_PROMISE_PAYMENT_CONFIRMED_MESSAGE",
        "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_NEW",
        "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_CONFIRMED",
        "TRACKING_PROMISE_PREPARING_NEXT_PICKUP",
        "TRACKING_PROMISE_PREPARING_NEXT_DELIVERY",
        "TRACKING_PROMISE_READY_DELIVERY_NEXT",
        "TRACKING_PROMISE_READY_PICKUP_NEXT",
        "TRACKING_PROMISE_READY_PICKUP_ACTIVE_NOTIFICATION",
        "TRACKING_PROMISE_READY_DELIVERY_ACTIVE_NOTIFICATION",
        "TRACKING_PROMISE_DISPATCHED_MESSAGE",
        "TRACKING_PROMISE_DISPATCHED_NEXT",
        "TRACKING_PROMISE_DELIVERED_NEXT",
        "TRACKING_PROMISE_CANCELLED_NEXT",
        "TRACKING_PROMISE_ACTIVE_UPDATE_NOTIFICATION",
        "TRACKING_PROMISE_RECEIVED_NEXT",
        "TRACKING_STEP_RECEIVED",
        "TRACKING_STEP_AVAILABILITY_CONFIRMED",
        "TRACKING_STEP_PAYMENT_CONFIRMED",
        "TRACKING_STEP_PREPARING",
        "TRACKING_STEP_READY_PICKUP",
        "TRACKING_STEP_READY_DELIVERY",
        "TRACKING_STEP_DISPATCHED",
        "TRACKING_STEP_DELIVERED",
        "TRACKING_STEP_COMPLETED",
        "TRACKING_STEP_CANCELLED",
        "PAYMENT_PAGE_TITLE",
        "PAYMENT_PAGE_META_DESCRIPTION",
        "PAYMENT_ORDER_REF_LABEL",
        "PAYMENT_TOTAL_LABEL",
        "PAYMENT_DEV_CONFIRM_CTA",
        "PAYMENT_ERROR_TITLE",
        "PAYMENT_ERROR_MESSAGE",
        "PAYMENT_RETRY_CTA",
        "PAYMENT_PIX_INSTRUCTION",
        "PAYMENT_REDIRECTING_PREFIX",
        "PAYMENT_REDIRECTING_SUFFIX",
        "PAYMENT_PIX_REGENERATE_CTA",
        "PAYMENT_VIEW_ORDER_CTA",
        "PAYMENT_CANCELLED",
        "PAYMENT_CANCELLED_DETAILS_CTA",
    ):
        assert key in OMOTENASHI_DEFAULTS
