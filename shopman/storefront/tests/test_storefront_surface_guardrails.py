from pathlib import Path

STOREFRONT_ROOT = Path(__file__).parents[1]
TEMPLATES = STOREFRONT_ROOT / "templates" / "storefront"
STATIC_JS = STOREFRONT_ROOT / "static" / "storefront" / "js"


def _read_template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def test_cart_actions_helper_is_loaded_before_alpine():
    tokens = _read_template("partials/_tokens.html")

    assert "cart-actions.js" in tokens
    assert tokens.index("cart-actions.js") < tokens.index("alpinejs")


def test_catalog_cards_use_canonical_cart_line_factory():
    grid = _read_template("partials/_catalog_item_grid.html")
    availability = _read_template("partials/availability_preview.html")

    assert "window.ShopmanCart.line" in grid
    assert "window.ShopmanCart.line" in availability
    assert "X-Shopman-Error-UI" not in grid
    assert "stock-error-modal" not in grid
    assert "X-Shopman-Error-UI" not in availability
    assert "stock-error-modal" not in availability


def test_menu_search_is_accent_insensitive_and_observable():
    menu = _read_template("menu.html")

    assert "normalize('NFD')" in menu
    assert r"/[\u0300-\u036f]/g" in menu
    assert "loadSearchIndex()" in menu
    assert "window.ShopmanCart.notify" in menu
    assert "role=\"searchbox\"" in menu
    assert "aria-live=\"polite\"" in menu


def test_checkout_when_step_blocks_ambiguous_advance():
    checkout = _read_template("checkout.html")

    assert "canAdvance(s)" in checkout
    assert "continueFrom(s)" in checkout
    assert "Escolha data e horário para seguir." in checkout
    assert ":disabled=\"!canAdvance('when')\"" in checkout


def test_pdp_does_not_use_multiline_single_line_django_comments():
    pdp = _read_template("product_detail.html")

    assert "{# Add button" not in pdp
    assert "requested quantity lives in this Alpine scope" in pdp


def test_cart_actions_reports_rich_stock_errors_and_network_errors():
    js = (STATIC_JS / "cart-actions.js").read_text(encoding="utf-8")

    assert "X-Shopman-Error-UI" in js
    assert "mountStockErrorModal" in js
    assert "Sem conexão. Verifique sua internet." in js
    assert "Não foi possível atualizar o carrinho" in js


def test_cart_surface_keeps_mobile_totals_readable():
    cart = _read_template("cart.html")
    cart_page = _read_template("partials/_cart_page_content.html")
    drawer = _read_template("partials/cart_drawer.html")

    assert "{% block title %}{% omotenashi 'CART_PAGE_TITLE'" in cart
    assert "flex flex-col sm:flex-row sm:items-center sm:justify-between" in cart_page
    assert "self-end sm:self-auto shrink-0" in cart_page
    assert "flex flex-wrap items-center justify-between" in drawer
    assert "ml-auto shrink-0" in drawer
