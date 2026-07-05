# E2E do Gestor (Playwright)

Backend-independentes: mock backend leve (`mockBackend.mjs`, sessão autenticada + uma
fila) + o app (build de produção em `baseURL '/'`). `npm run test:e2e`.

## Coberto

- **`board.spec.ts`** — o mock devolve sessão de operador autenticada (sem lock) + uma
  fila com um card; o Gestor passa dos gates (login/lock) e renderiza o card com cliente,
  itens e total.
- **`resilience.spec.ts`** — `<OfflineBanner>` (kit) aparece ao cair a rede e some ao voltar.

## Fora daqui (Django real — reviewer local)

- **Login efetivo** + sessão cross-subdomínio `.boulangerie`.
- **Lock (Opção C)** — PIN/crachá quando `SHOPMAN_REQUIRE_ACTIVE_OPERATOR` está ON.
- **Ações** (confirmar/avançar/recusar/atribuir) + SSE realtime + catálogo/expositores.
