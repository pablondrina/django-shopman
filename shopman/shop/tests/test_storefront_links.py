"""Fonte única de URL da loja Nuxt — caminhos canônicos + cutover por 1 knob."""
from shopman.shop.services import storefront_links as sl


def test_paths_are_nuxt_canonical():
    # Caminhos da loja NUXT (não os antigos do Django legado).
    assert sl.path_home() == "/"
    assert sl.path_menu() == "/menu"
    assert sl.path_product("BAGUETE") == "/product/BAGUETE"
    assert sl.path_cart() == "/cart"
    assert sl.path_checkout() == "/checkout"
    assert sl.path_order_tracking("ORD-001") == "/tracking/ORD-001"
    assert sl.path_order_payment("ORD-001") == "/pedido/ORD-001/pagamento"
    assert sl.path_account() == "/account"


def test_absolute_urls_use_base(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://nelson.com"
    assert sl.order_payment_url("ORD-1") == "https://nelson.com/pedido/ORD-1/pagamento"
    assert sl.order_tracking_url("ORD-1") == "https://nelson.com/tracking/ORD-1"
    assert sl.product_url("BAGUETE") == "https://nelson.com/product/BAGUETE"
    assert sl.home_url() == "https://nelson.com/"


def test_base_trailing_slash_is_normalized(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://nelson.com/"
    assert sl.storefront_base_url() == "https://nelson.com"
    assert sl.order_payment_url("X") == "https://nelson.com/pedido/X/pagamento"


def test_empty_base_returns_relative_path(settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = ""
    assert sl.order_payment_url("X") == "/pedido/X/pagamento"
    assert sl.home_url() == "/"


def test_domain_cutover_is_a_single_knob(settings):
    # Trocar a base reaponta TODOS os links de cliente de uma vez (staging → prod).
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://staging.example/thing"
    assert sl.order_tracking_url("R") == "https://staging.example/thing/tracking/R"
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://nelson.com"
    assert sl.order_tracking_url("R") == "https://nelson.com/tracking/R"
