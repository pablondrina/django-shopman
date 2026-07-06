# E2E do KDS (kds-nuxt)

Playwright **backend-independente**: o `mockBackend.mjs` ramifica pelo cookie `e2e_session`
que o BFF encaminha ao Django. Sem cookie → 403 nos endpoints de operador (aparece o gate
de login); com `e2e_session=authed` → sessão autenticada + estações + board vazio. O board
público do cliente (`/kds/cliente/`) responde 200 sempre, então `/retirada` renderiza sem
sessão. Um único mock+build cobre gate-de-login E telas de operador E o painel público.

```bash
npm run test:e2e
```

## O que cobre

- **guards.spec** — telas de operador atrás do gate; sessão autenticada → seletor de
  estações + rail; `/retirada` (público) renderiza SEM sessão de operador e FORA do rail.
  (Sem teste de 404: `pages/[ref].vue` torna todo path de um segmento um ref de estação
  válido — não há 404 genérico, análogo ao POS view-única.)
- **resilience.spec** — `OfflineBanner` aparece/some com a rede.

## O que fica para o reviewer local (Django real)

Login efetivo, lock (Opção C), ações reais (marcar item, finalizar, expedir, recall), o beep
de novo ticket e o SSE ao vivo exigem a stack completa + gateway (SSE é same-origin).

## Portas

- App (build de produção do e2e): `127.0.0.1:3103` (distinta do dev server em `:3003`)
- Mock backend: `127.0.0.1:8798` (evita colidir com os mocks do Gestor `:8796`/Fournil `:8797`)
