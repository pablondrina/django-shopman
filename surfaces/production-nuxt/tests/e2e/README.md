# E2E do Fournil (production-nuxt)

Playwright **backend-independente**: um mock backend (`mockBackend.mjs`) serve uma sessão
de operador autenticada + boards de produção vazios + o cardápio público do menuboard. O
app é buildado com `NUXT_APP_BASE_URL=/` (produção usa `/`) e apontado ao mock via
`NUXT_DJANGO_BASE_URL`.

```bash
npm run test:e2e
```

## O que cobre

- **guards.spec** — telas de operador atrás do gate de login; painel público (`/menuboard`)
  renderiza SEM sessão de operador (não é embrulhado pelo gate).
- **resilience.spec** — `OfflineBanner` aparece quando o contexto vai offline.

## O que fica para o reviewer local (Django real)

Login efetivo, lock (Opção C), troca de operador, planejar/iniciar/concluir com dados
reais, e o rollover de meia-noite do painel exigem a stack completa + gateway. Rodam contra
o Django real; ver os specs marcados com `test.skip` e um comentário.

## Como funciona a sessão (mock ramificado por cookie)

O `mockBackend.mjs` ramifica pelo cookie `e2e_session` que o BFF encaminha ao Django:
sem cookie → 403 nos endpoints de operador (aparece o gate de login); com
`e2e_session=authed` → sessão autenticada + boards vazios. O `/storefront/menu/` é
público (200 sempre). Assim um único mock+build cobre gate-de-login E telas de operador.

## Portas

- App (build de produção do e2e): `127.0.0.1:3105` (distinta do dev server em `:3005`,
  para não reusar um dev server aberto que aponta ao Django real)
- Mock backend: `127.0.0.1:8797` (evita colidir com o mock do Gestor em `:8796`)
