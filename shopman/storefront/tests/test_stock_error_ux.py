"""Regression: rich stock-error UX from the storefront menu/PDP cards.

When a cart quantity mutation fails due to stock, the server must respond with a
422 + `X-Shopman-Error-UI: 1` + `HX-Retarget: #stock-error-modal` + HTML
that the client injects into the sentinel. The global `htmx:responseError`
handler (in base.html) skips the generic toast when the marker header is
present, so the user always sees the rich modal (available qty + substitutes)
instead of "algo deu errado".

Previously, the menu-grid card used `htmx.ajax().then()` without inspecting
the response status, so a 422 resulted in the generic toast. This test
locks down the new contract.
"""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import unquote

import pytest
from django.test import Client

from shopman.shop.services.cart import CartUnavailableError


@pytest.fixture
def product(db):
    from shopman.offerman.models import Listing, ListingItem, Product
    p = Product.objects.create(
        sku="STOCK-ERR-TEST",
        name="Pão Teste",
        base_price_q=500,
        is_published=True,
    )
    listing = Listing.objects.get_or_create(
        ref="web", defaults={"name": "Web", "is_active": True},
    )[0]
    ListingItem.objects.get_or_create(
        listing=listing, product=p,
        defaults={"price_q": 500, "is_published": True},
    )
    return p


def test_cart_set_qty_sends_rich_error_ui_marker(db, product):
    """422 + X-Shopman-Error-UI + HX-Retarget + modal HTML (not generic toast)."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=5,
        available_qty=2,
        error_code="below_stock",
        is_paused=False,
        substitutes=[],
    )
    with patch(
        "shopman.storefront.cart.CartService.add_item", side_effect=exc,
    ):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "5"})

    assert resp.status_code == 422, "stock error must be 422, not 200 or 500"
    assert resp["X-Shopman-Error-UI"] == "1", (
        "marker is what tells base.html error handler to skip the generic toast"
    )
    assert resp["HX-Retarget"] == "#stock-error-modal"
    assert resp["HX-Reswap"] == "innerHTML"
    body = resp.content.decode("utf-8")
    assert "Adicionar 2 dispon" in body, (
        "primary CTA must appear for shortage with partial stock remaining"
    )


def test_cart_set_qty_non_numeric_qty_rejects_without_mutation(db, product):
    client = Client()
    with patch("shopman.storefront.cart.CartService.add_item") as mock_add:
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "abc"})

    assert resp.status_code == 400
    mock_add.assert_not_called()


def test_cart_set_qty_clamps_absurd_qty(db, product):
    client = Client()
    with patch("shopman.storefront.cart.CartService.add_item") as mock_add:
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "1000000"})

    assert resp.status_code == 200
    assert mock_add.call_args.kwargs["qty"] == 99


def test_cart_set_qty_success_exposes_lightweight_summary_headers(db, product):
    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})
    client = Client()
    with patch(
        "shopman.shop.services.availability.reserve",
        return_value={
            "ok": True,
            "hold_id": "fake-hold",
            "available_qty": 999,
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
        },
    ):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "2"})

    assert resp.status_code == 200
    assert resp["X-Cart-Count"] == "2"
    assert resp["X-Cart-Subtotal-Q"] == "1000"
    assert unquote(resp["X-Cart-Subtotal-Display"]) == "R$ 10,00"


def test_cart_set_qty_can_remove_unpublished_existing_line(db, product):
    """A stale cart line must remain removable after the product leaves the public catalog."""
    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})
    client = Client()
    with patch(
        "shopman.shop.services.availability.reserve",
        return_value={
            "ok": True,
            "hold_id": "fake-hold",
            "available_qty": 999,
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
        },
    ):
        add = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "1"})
    assert add.status_code == 200

    product.is_published = False
    product.save(update_fields=["is_published"])

    remove = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "0"})

    assert remove.status_code == 200
    assert "cart_session_key" in client.session
    summary = client.get("/cart/summary/")
    assert summary.status_code == 200
    assert "hidden" in summary.content.decode("utf-8")


def test_cart_set_qty_stock_error_contract_is_rich(db, product):
    """The SKU-based stepper (menu/PDP) must get the rich stock-error treatment."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=3,
        available_qty=0,
        error_code="below_stock",
        is_paused=False,
        substitutes=[],
    )
    with patch(
        "shopman.storefront.cart.CartService.add_item", side_effect=exc,
    ):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "3"})
    assert resp.status_code == 422
    assert resp["X-Shopman-Error-UI"] == "1"
    assert resp["HX-Retarget"] == "#stock-error-modal"
    body = resp.content.decode("utf-8")
    assert "não está disponível no momento" in body, (
        "sold-out shortage must show unavailable copy"
    )


def test_stock_error_modal_html_has_penguin_tokens(db, product):
    """Modal must use Penguin UI tokens (bg-surface-alt, on-surface-strong),
    never v1 utility classes (modal-card, text-foreground, text-muted-foreground).
    """
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=99,
        available_qty=1,
        error_code="below_stock",
        is_paused=False,
        substitutes=[],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "99"})
    body = resp.content.decode("utf-8")

    # v1 tokens that must NOT appear
    for v1_token in ("modal-card", "modal-overlay", "text-muted-foreground",
                     "text-primary-foreground", "bg-primary-hover"):
        assert v1_token not in body, f"modal still references v1 token '{v1_token}'"

    # Penguin tokens that MUST appear
    assert "bg-surface-alt" in body, "modal must use Penguin surface-alt"
    assert "text-on-surface-strong" in body


# ── Actionable modal contract (STOCK-UX-PLAN) ──────────────────────────


def test_modal_has_primary_action_when_stock_remains(db, product):
    """available_qty > 0 → primary CTA 'Adicionar N disponíveis' calling
    cart_set_qty with qty=available_qty and isAlternative=false."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=10,
        available_qty=3,
        error_code="below_stock",
        is_paused=False,
        substitutes=[],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "10"})
    body = resp.content.decode("utf-8")

    import re as _re
    assert "Adicionar 3 dispon" in body, "primary CTA must label 'Adicionar N disponíveis'"
    # pickAction(sku, 3, 'Pão Teste', false) — false = not an alternative
    assert _re.search(r"pickAction\([^)]+,\s*3,\s*['\"][^'\"]+['\"],\s*false\)", body), (
        "primary CTA must pass qty=available and isAlternative=false"
    )


def test_modal_renders_substitutes_as_one_click_buttons(db, product):
    """Each alternative is a full-width button that calls pickAction with
    isAlternative=true and qty=target_qty."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=1,
        available_qty=0,
        error_code="below_stock",
        is_paused=False,
        substitutes=[
            {"sku": "BAGUETE-ALT", "name": "Baguete Alternativa",
             "price_display": "R$ 11,00", "price_q": 1100,
             "available_qty": 5, "can_order": True, "target_qty": 1},
            {"sku": "CROISS-ALT", "name": "Croissant Alternativo",
             "price_display": "R$ 8,50", "price_q": 850,
             "available_qty": 3, "can_order": True, "target_qty": 1},
        ],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "1"})
    body = resp.content.decode("utf-8")

    import re as _re
    assert "Baguete Alternativa" in body
    assert "R$ 11,00" in body
    assert "Croissant Alternativo" in body
    # Each alt emits pickAction(sku, target_qty, name, true) — true = alternative
    assert _re.search(
        r"BAGUETE.{0,10}ALT[^)]*,\s*1,\s*['\"]Baguete Alternativa['\"],\s*true",
        body,
    ), "first alternative must pickAction with isAlternative=true"
    assert _re.search(
        r"CROISS.{0,10}ALT[^)]*,\s*1,\s*['\"]Croissant Alternativo['\"],\s*true",
        body,
    ), "second alternative must pickAction with isAlternative=true"


def test_sold_out_without_substitutes_shows_no_primary_action(db, product):
    """available=0 + no substitutes → only close button; no primary CTA."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=1,
        available_qty=0,
        error_code="below_stock",
        is_paused=False,
        substitutes=[],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "1"})
    body = resp.content.decode("utf-8")

    assert "Adicionar" not in body or "Adicionar ao carrinho" not in body, (
        "no primary CTA when nothing to add"
    )
    # Close button remains
    assert "Fechar" in body


# ── Return flow (WP-STOCK-UX-1b): picker_origin + redirect decision ────


def test_modal_tags_picker_origin_pdp_when_called_from_pdp(db, product):
    """Modal embeds origin='pdp' so the client-side pickAction can redirect
    to /cart/ after picking an alternative."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=1,
        available_qty=0,
        error_code="below_stock",
        is_paused=False,
        substitutes=[],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post(
            "/cart/set-qty/",
            {"sku": product.sku, "qty": "1"},
            HTTP_HX_CURRENT_URL="https://example.com/produto/STOCK-ERR-TEST/",
        )
    body = resp.content.decode("utf-8")
    assert "origin: 'pdp'" in body, (
        "Alpine component must carry origin='pdp' so redirect branch fires"
    )


def test_modal_tags_picker_origin_menu_when_called_from_home(db, product):
    """Modal embeds origin='menu' so substitutes stay in place."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=1,
        available_qty=0,
        error_code="below_stock",
        is_paused=False,
        substitutes=[],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post(
            "/cart/set-qty/",
            {"sku": product.sku, "qty": "1"},
            HTTP_HX_CURRENT_URL="https://example.com/",
        )
    body = resp.content.decode("utf-8")
    assert "origin: 'menu'" in body


def test_modal_tags_picker_origin_cart_when_called_from_cart(db, product):
    """Origin 'cart' also stays in place (no redirect)."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=1,
        available_qty=0,
        error_code="below_stock",
        is_paused=False,
        substitutes=[],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post(
            "/cart/set-qty/",
            {"sku": product.sku, "qty": "1"},
            HTTP_HX_CURRENT_URL="https://example.com/cart/",
        )
    body = resp.content.decode("utf-8")
    assert "origin: 'cart'" in body


# ── Kintsugi variant tests (WP-GAP-14) ────────────────────────────────────


def test_planned_variant_shows_reserve_cta(db, product):
    """is_planned=True → 'planned' variant with 'Reservar no próximo lote' CTA."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=2,
        available_qty=0,
        error_code="insufficient_stock",
        is_paused=False,
        substitutes=[],
        is_planned=True,
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "2"})
    assert resp.status_code == 422
    body = resp.content.decode("utf-8")
    assert "Reservar no próximo lote" in body, (
        "planned variant must offer a pre-reserve CTA"
    )
    assert "A caminho" in body, (
        "planned variant title comes from KINTSUGI_PLANNED_OFFER omotenashi key"
    )


def test_paused_variant_shows_warm_copy(db, product):
    """is_paused=True → 'paused' variant with warm 'Voltamos em breve' copy."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=1,
        available_qty=0,
        error_code="paused",
        is_paused=True,
        substitutes=[],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "1"})
    assert resp.status_code == 422
    body = resp.content.decode("utf-8")
    assert "Voltamos em breve" in body, (
        "paused variant title comes from KINTSUGI_PAUSED_COPY omotenashi key"
    )
    assert "Adicionar" not in body or "Reservar" not in body, (
        "paused variant must not show add/reserve CTAs"
    )


def test_substitute_image_rendered_when_provided(db, product):
    """When a substitute has image_url, an <img> element appears in the modal."""
    client = Client()
    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=1,
        available_qty=0,
        error_code="below_stock",
        is_paused=False,
        substitutes=[
            {
                "sku": "IMG-ALT",
                "name": "Pão com Imagem",
                "image_url": "https://cdn.test/pao.jpg",
                "price_display": "R$ 7,00",
                "price_q": 700,
                "available_qty": 10,
                "can_order": True,
                "target_qty": 1,
            }
        ],
    )
    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        resp = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "1"})
    body = resp.content.decode("utf-8")
    assert "https://cdn.test/pao.jpg" in body, (
        "substitute with image_url must render an <img> with that URL"
    )
