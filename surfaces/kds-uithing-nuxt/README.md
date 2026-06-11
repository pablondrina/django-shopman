# Shopman POS UI Thing Nuxt

Headless POS surface used to validate that a new operator UI can attach to the
Shopman POS projection/action contract without copying business rules.

## Setup

```bash
npm install
```

## Development Server

Start the surface on `http://127.0.0.1:3002/`:

```bash
npm run dev
```

Nuxt will choose another port, such as `3001`, if `3002` is already in use.

The API proxy targets `http://127.0.0.1:8000` by default. Override it with
`NUXT_DJANGO_BASE_URL` when Django is elsewhere.

## Operator access

The POS does not own credentials. Backstage endpoints use the canonical Django
session and require a staff user with `backstage.operate_pos`.

When the session is missing or unauthorized, the Nuxt surface links to
the Django admin login on the Django public base URL. Production defaults can
return to `/pos/`; local development returns to `/admin/` so the operator can
log in, keep the POS tab open, and click "Já entrei". Override the return path
with `NUXT_POS_LOGIN_NEXT_PATH` when a deployment serves the POS somewhere else.

For local development, keep Django and Nuxt on the same hostname, such as
`127.0.0.1`, so Django session and CSRF cookies are visible to both ports.

## Production

```bash
npm run build
```

## Tests

```bash
npm run test
```

The UI reads `GET /api/v1/backstage/pos/` and submits only projection-provided
POS actions. Price, stock, fulfillment validation, status, and order persistence
remain in the Django/Shopman contract.

Current POS capabilities consumed from the projection include tab lifecycle,
cash runtime/actions, checkout review/close, customer lookup with saved
addresses and memory, delivery address autocomplete/reverse geocode metadata,
recent sale correction, and idempotent replay via `client_request_id`.

The tab reference contract is `tab_ref`. Numeric refs up to 8 digits keep the
zero-padded storage shape, while alphanumeric operator references are accepted
as short text and remain owned by the canonical POS service/projection layer.

`tab_lifecycle.allows_direct_checkout_without_tab` enables quick sales without a
comanda for direct checkout. Any draft without a tab must still be associated
through the UI Thing dialog before save/pause or before switching to another
comanda.
