from shopman.stockman.protocols.sku import SkuInfo, SkuValidationResult


class OrderableSkuValidator:
    def validate_sku(self, sku: str) -> SkuValidationResult:
        return SkuValidationResult(
            valid=True,
            sku=sku,
            product_name=sku,
            is_published=True,
            is_sellable=True,
        )

    def validate_skus(self, skus: list[str]) -> dict[str, SkuValidationResult]:
        return {sku: self.validate_sku(sku) for sku in skus}

    def get_sku_info(self, sku: str) -> SkuInfo | None:
        return SkuInfo(
            sku=sku,
            name=sku,
            description=None,
            is_published=True,
            is_sellable=True,
            unit="un",
            category=None,
            base_price_q=None,
            availability_policy="planned_ok",
            shelflife_days=None,
            metadata=None,
        )

    def search_skus(
        self,
        query: str,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list[SkuInfo]:
        return []


class PausedSkuValidator(OrderableSkuValidator):
    def validate_sku(self, sku: str) -> SkuValidationResult:
        return SkuValidationResult(
            valid=True,
            sku=sku,
            product_name=sku,
            is_published=True,
            is_sellable=False,
        )

    def get_sku_info(self, sku: str) -> SkuInfo | None:
        return SkuInfo(
            sku=sku,
            name=sku,
            description=None,
            is_published=True,
            is_sellable=False,
            unit="un",
            category=None,
            base_price_q=None,
            availability_policy="planned_ok",
            shelflife_days=None,
            metadata=None,
        )


class StockOnlySkuValidator(OrderableSkuValidator):
    def get_sku_info(self, sku: str) -> SkuInfo | None:
        return SkuInfo(
            sku=sku,
            name=sku,
            description=None,
            is_published=True,
            is_sellable=True,
            unit="un",
            category=None,
            base_price_q=None,
            availability_policy="stock_only",
            shelflife_days=None,
            metadata=None,
        )


class DemandOkSkuValidator(OrderableSkuValidator):
    def get_sku_info(self, sku: str) -> SkuInfo | None:
        return SkuInfo(
            sku=sku,
            name=sku,
            description=None,
            is_published=True,
            is_sellable=True,
            unit="un",
            category=None,
            base_price_q=None,
            availability_policy="demand_ok",
            shelflife_days=None,
            metadata=None,
        )
