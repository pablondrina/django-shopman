from pathlib import Path

STOREFRONT_ROOT = Path(__file__).parents[1]
TEMPLATES = STOREFRONT_ROOT / "templates" / "storefront"
STATIC_JS = STOREFRONT_ROOT / "static" / "storefront" / "js"
CSS_SOURCE = STOREFRONT_ROOT.parents[1] / "static" / "src" / "style.css"


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


def test_mobile_menu_layers_above_menu_pill_bar():
    base = _read_template("base.html")
    menu = _read_template("menu.html")

    assert "z-[80]" in base
    assert "z-[70]" in base
    assert "sticky top-0 z-50" in menu
    assert "fixed left-0 right-0 bottom-0 z-40" in menu


def test_menu_pills_keep_scroll_spy_centering():
    menu = _read_template("menu.html")

    assert "queueScrollSpy()" in menu
    assert "requestAnimationFrame" in menu
    assert "updateActiveFromScroll()" in menu
    assert "centerPillInRail(closest)" in menu
    assert menu.index('<div x-data="menuNav()"') < menu.index('<section id="section-{{ section.ref }}"')
    assert menu.index("catalog_search_index_json|json_script") < menu.index("px-4 py-6 space-y-10")


def test_ios_form_focus_does_not_auto_zoom():
    css = CSS_SOURCE.read_text(encoding="utf-8")
    base = _read_template("base.html")

    assert "maximum-scale" not in base
    assert "@media (max-width: 767px)" in css
    assert "font-size: 16px" in css


def test_customer_surfaces_keep_focus_first_hierarchy():
    menu = _read_template("menu.html")
    pdp = _read_template("product_detail.html")
    login = _read_template("login.html")
    cart_page = _read_template("partials/_cart_page_content.html")

    assert "order-2 md:order-1 aspect-video sm:aspect-square" in pdp
    assert "order-1 md:order-2 flex flex-col" in pdp
    assert "text-3xl" not in pdp
    assert "h-28 sm:h-36" in login
    assert "h-44 sm:h-56" not in login
    assert "text-2xl lg:text-3xl" not in menu
    assert "text-2xl lg:text-3xl" not in cart_page


def test_customer_surfaces_use_canonical_icon_scale():
    css = CSS_SOURCE.read_text(encoding="utf-8")
    menu = _read_template("menu.html")
    pdp = _read_template("product_detail.html")
    grid = _read_template("partials/_catalog_item_grid.html")
    drawer = _read_template("partials/cart_drawer.html")
    bottom_nav = _read_template("partials/_bottom_nav.html")

    for token in ("icon-xs", "icon-sm", "icon-md", "icon-lg", "icon-xl", "icon-display"):
        assert f".{token}" in css

    assert "material-symbols-rounded icon-lg" in menu
    assert "material-symbols-rounded icon-display" in pdp
    assert "material-symbols-rounded icon-xl" in grid
    assert "material-symbols-rounded icon-display" in drawer
    assert "material-symbols-rounded icon-md" in bottom_nav


def test_viewport_chrome_follows_top_surface_color():
    base = _read_template("base.html")
    tokens = _read_template("partials/_tokens.html")
    css = CSS_SOURCE.read_text(encoding="utf-8")

    assert 'apple-mobile-web-app-status-bar-style" content="{% if shop_status.message %}' in base
    assert "black-translucent" not in base
    assert "syncViewportChrome()" in tokens
    assert "document.elementFromPoint" in tokens
    assert "--shopman-safe-top-color" in tokens
    assert "h.style.backgroundColor = color" in tokens
    assert "env(safe-area-inset-top)" in css
    assert "body::before" in css
