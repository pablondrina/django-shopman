"""
Offerman signals.

Signals:
    product_created:
        Sent after a new Product is saved for the first time.

        Kwargs:
            sender: Product class
            instance: The Product instance that was created
            sku: str — the product SKU

        Example handler::

            from shopman.offerman.signals import product_created

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

            from shopman.offerman.signals import price_changed

            def on_price_changed(sender, instance, sku, old_price_q, new_price_q, **kwargs):
                logger.info("Price for %s changed: %d -> %d", sku, old_price_q, new_price_q)

            price_changed.connect(on_price_changed)

    product_updated:
        Sent after an existing Product's projectable fields change
        (name, short/long description, is_published, is_sellable).

        Kwargs:
            sender: Product class
            instance: The Product instance
            sku: str — the product SKU

    availability_changed:
        Sent after a ListingItem's availability changes on a channel
        (is_published or is_sellable) — a per-channel pause/resume.

        Kwargs:
            sender: ListingItem class
            instance: The ListingItem instance
            listing_ref: str — the listing code (channel)
            sku: str — the product SKU
"""

from django.dispatch import Signal

product_created = Signal()
product_updated = Signal()
price_changed = Signal()
availability_changed = Signal()
