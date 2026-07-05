# E2E da Central de Apps (Playwright)

Backend-independentes: mock backend leve (`mockBackend.mjs`) + o app (build de produção
em `baseURL '/'`). `npm run test:e2e`.

## Coberto

- **`hub.spec.ts`** — o mock devolve uma projection de hub com tiles; a Central renderiza
  a saudação + a grade de apps; cada tile linka pra sua superfície (Loja = config abre em
  nova aba).
- **`resilience.spec.ts`** — banner offline (kit) via `context.setOffline`.

## Fora daqui (Django real — reviewer local)

- **Login efetivo** + sessão cross-subdomínio `.boulangerie`.
- **Filtragem por permissão** — os tiles reais dependem das perms do operador
  (coberto no lado Django: `shopman/backstage/tests/test_api_hub_surface.py`).
- **Gate de login** — mesmo padrão da shell provado no `pos-nuxt` (kit compartilhado).
