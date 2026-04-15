# Demo Personas — Proto Scenarios Tool

A dev/QA helper for simulating storefront personas on the fly. It lives outside the
production bundle at [`tools/demo-scenarios/proto-scenarios.js`](../../tools/demo-scenarios/proto-scenarios.js)
and is intentionally not wired into any template.

## What it does

Includes a collapsible floating panel in the bottom-right of the page with two tabs:

- **Personas** — 10 predefined contexts (returning vs new customer, near/far distance,
  morning/lunch/night, store open/closed, geolocation granted/denied/marginal).
- **Controles** — granular toggles to hand-tune hour, distance, and geolocation state
  without picking a preset.

When a preset is clicked, the script reaches into the Alpine root component
(`document.querySelector('[x-data]').__x.$data`) and rewrites observable variables
(`hour`, `minute`, `userDistance`, `isReturning`, `geolocationDenied`, …). State is
persisted in `sessionStorage` under `proto_scenario_state` so the chosen persona
survives page navigations within the same tab.

## Persona catalog

| id                | label                                   | notes                                 |
|-------------------|-----------------------------------------|---------------------------------------|
| `maria-morning`   | Maria · Fiel · Manhã · Perto            | 9h, 1.2km, returning                  |
| `maria-early`     | Maria · Fiel · Cedinho · Antes de Abrir | 6h30, 0.8km, store closed             |
| `lunch-rush`      | Carlos · Fiel · Almoço · Perto          | 12h, 0.5km, returning                 |
| `maria-night`     | Maria · Fiel · Noite · Fechado          | 20h, 1.2km, store closed              |
| `joao-near`       | João · Novo · Manhã · Perto             | 10h, 2.0km, first visit               |
| `joao-marginal`   | João · Novo · Zona Marginal             | 14h, 6.0km, first visit               |
| `ana-outside`     | Ana · Novo · Fora da Zona               | first visit, out of delivery range    |
| `pedro-denied`    | Pedro · Geoloc Negada                   | geolocationDenied = true              |
| `sofia-loading`   | Sofia · Geoloc Carregando               | geolocationLoading = true             |
| `clara-returning` | Clara · Retornando · Confirmada         | locationConfirmed = true              |

(See the `PRESETS` array at the top of `proto-scenarios.js` for the complete,
authoritative list — the table above is a convenience reference.)

## How to reactivate

The script is not bundled. To use it on a local dev run, either:

1. **Inline include** — add before the closing `</body>` of a template you are
   iterating on:

   ```html
   {% if debug %}
     <script src="{% static 'storefront/v2/js/proto-scenarios.js' %}"></script>
   {% endif %}
   ```

   and copy the file into `shopman/shop/static/storefront/v2/js/` for the
   duration of your dev session. Do **not** commit that copy.

2. **Bookmarklet** — paste the file contents into a browser bookmarklet and
   trigger it from any storefront page.

3. **DevTools snippet** — save it as a Chrome DevTools Snippet (Sources → Snippets)
   for one-click replay during manual QA.

## When to use

- Demoing closed/open/near/far store states to stakeholders without faking
  `localStorage` by hand.
- Reproducing the "geolocation denied" branch of checkout without flipping
  browser permissions.
- Exercising the "first visit vs returning customer" split on home/landing
  screens.

## When not to use

- **Never in production bundles.** The script rewrites reactive state in a way
  that bypasses all server-side validation and is strictly a rehearsal tool.
- **Not for automated tests.** Cypress/Playwright should drive the real Alpine
  component boundaries, not a sideband panel.

## Provenance

Extracted from the old `shopman/shop/web/templates/storefront/proto/` sandbox
during PROTO-EXTRACTION (see `docs/plans/completed/PROTO-EXTRACTION-PLAN.md`).
The proto directory itself was deleted — this tool and this guide are the
surviving artefacts.
