from pathlib import Path


ROOT = Path(__file__).parents[3]


def test_sse_triggers_use_safe_sku_parser():
    template_paths = [
        ROOT / "shopman/backstage/templates/pos/index.html",
        ROOT / "shopman/storefront/templates/storefront/partials/_catalog_item_grid.html",
        ROOT / "shopman/storefront/templates/storefront/product_detail.html",
    ]

    for path in template_paths:
        source = path.read_text(encoding="utf-8")
        assert "JSON.parse(event.data)" not in source, path
        assert "shopmanSseSku(event)" in source, path


def test_safe_sku_parser_is_available_on_sse_surfaces():
    backstage_base = (ROOT / "shopman/backstage/templates/gestor/base.html").read_text(encoding="utf-8")
    storefront_base = (ROOT / "shopman/storefront/templates/storefront/base.html").read_text(encoding="utf-8")

    assert "window.shopmanSseSku" in backstage_base
    assert "window.shopmanSseSku" in storefront_base
