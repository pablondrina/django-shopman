"""
Shopman Pricing Contrib — Precificação de itens.

Uso:
    from shopman.pricing.protocols import PricingBackend
    from shopman.pricing.modifiers import ItemPricingModifier

Para uso simples (Product.price_q):
    from shopman.pricing.adapters.simple import SimplePricingBackend
"""

from .protocols import PricingBackend

__all__ = ["PricingBackend"]
