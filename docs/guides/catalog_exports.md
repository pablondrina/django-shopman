# Neutral Catalog Exports

`shopman.shop.services.catalog_exports` produces a platform-neutral payload from
an Offerman listing. It does not call Google, WhatsApp, Meta/Instagram, or any
external API.

Adapters should:

1. Call `build_catalog_export(listing_ref="google")` or another listing/channel ref.
2. Translate each neutral item field (`sku`, `name`, `description`, `images`,
   `price`, `availability`, `status`, `metadata`) to the target platform schema.
3. Keep platform IDs, sync cursors, and API responses in adapter-owned metadata,
   not in the neutral contract.

Suggested mapping:

- Google Merchant: map `ref` to item id, `price.amount_q` to BRL price,
  `availability.status` to the platform availability enum.
- WhatsApp Catalog: map `name`, `description`, `images`, and `price` directly;
  store WhatsApp product IDs in adapter metadata.
- Meta/Instagram: map `sku`/`ref` to retailer id, `images` to media URLs, and
  preserve `metadata` for category or collection hints.
