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

The API proxy targets `http://127.0.0.1:8000` by default. Override it with
`NUXT_DJANGO_BASE_URL` when Django is elsewhere.

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
