# E2E do POS (Playwright)

E2E **backend-independentes**: sobem um mock backend leve (`mockBackend.mjs`) e o app
(build de produção servido em `baseURL '/'`) para exercitar comportamentos que **não
dependem de dados de negócio**.

```bash
npm run test:e2e          # sobe mock + build + serve + roda os specs
npm run test:e2e -- --ui  # modo interativo
```

O `playwright.config.ts` faz `nuxt build && node .output/server/index.mjs` com
`NUXT_APP_BASE_URL=/` (produção usa `/pos/`) e aponta o BFF ao mock via
`NUXT_DJANGO_BASE_URL`. `reuseExistingServer` evita rebuild a cada corrida local.

## Coberto aqui

- **`guards.spec.ts`** — gate de login: a leitura do terminal (`/backstage/pos/`) 401a
  (mock) → o app sobe a tela de login no próprio caixa, com credenciais e botão
  desabilitado até preencher.
- **`resilience.spec.ts`** — banner offline: `<OfflineBanner>` (global, do operator-kit)
  aparece ao cair a rede e some ao voltar.

## Fora daqui (precisa de Django real — reviewer local)

Fluxos que exigem uma Projeção de terminal com dados:

- **lock screen / re-gate de PIN** — precisa de operadores provisionados.
- **re-gate de 401 no meio da sessão** — precisa de um shell carregado + um comando
  que 401e (a versão de carga já está coberta no gate de login).
- **comanda → produto → pagamento → cozinha** — o fluxo de venda ponta-a-ponta.
- **404** — o POS é view única (sem `pages/`/router), então não há superfície de 404.

Rode-os contra um Django semeado (`make seed`) apontando `NUXT_DJANGO_BASE_URL` ao
backend real.
