from decimal import Decimal
from unittest.mock import Mock, patch

from shopman.offerman.exceptions import CatalogError

from shopman.shop.services.stock import _expand_if_bundle


def test_stock_bundle_expansion_treats_not_a_bundle_as_simple_product(caplog):
    catalog = Mock()
    catalog.expand_bundle.side_effect = CatalogError("NOT_A_BUNDLE", sku="BAGUETE")

    with patch("shopman.shop.services.stock.get_adapter", return_value=catalog):
        result = _expand_if_bundle("BAGUETE", Decimal("1"))

    assert result == [{"sku": "BAGUETE", "qty": Decimal("1")}]
    assert "unexpected error expanding" not in caplog.text
