"""
Offering signals.

Signals:
    product_created:
        Sent after a new Product is saved for the first time.

        Kwargs:
            sender: Product class
            instance: The Product instance that was created
            sku: str — the product SKU

        Example handler::

            from shopman.offering.signals import product_created

            def on_product_created(sender, instance, sku, **kwargs):
                logger.info("New product: %s", sku)

            product_created.connect(on_product_created)

    price_changed:
        Sent after a ListingItem's price_q changes.

        Kwargs:
            sender: ListingItem class
            instance: The ListingItem instance
            listing_ref: str — the listing code
            sku: str — the product SKU
            old_price_q: int — previous price in centavos
            new_price_q: int — new price in centavos

        Example handler::

            from shopman.offering.signals import price_changed

            def on_price_changed(sender, instance, sku, old_price_q, new_price_q, **kwargs):
                logger.info("Price for %s changed: %d -> %d", sku, old_price_q, new_price_q)

            price_changed.connect(on_price_changed)
"""

from django.dispatch import Signal

product_created = Signal()
price_changed = Signal()
