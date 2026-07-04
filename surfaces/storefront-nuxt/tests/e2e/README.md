# E2E (Playwright) — storefront

Dois níveis, por dependência de dados:

## 1. Independentes de backend (rodam aqui, no CI)

`resilience.spec.ts` e `guards.spec.ts` cobrem comportamentos do app que não
precisam de dados de negócio: shell degradado com backend vazio, banner offline
(reconexão), guard de `/conta` (redireciona ao login), página 404 (noindex).

Sobem automaticamente um **mock backend** (`mockBackend.mjs`, respostas `{}`
rápidas) e o `nuxt preview` apontado a ele.

```bash
npm run build          # e2e roda sobre o preview de produção
npm run test:e2e
```

## 2. Fluxo crítico com dados (`criticalFlow.spec.ts` — reviewer local)

menu → PDP → carrinho → checkout → tracking precisa do **Django real** com
`make seed`. Marcado `skip` por padrão. Para rodar localmente:

```bash
# terminal 1: Django semeado
make run   # (ou o servidor em :8000 com make seed feito)

# terminal 2: preview apontado ao Django real + specs
NUXT_DJANGO_BASE_URL=http://127.0.0.1:8000 npm run preview
npx playwright test tests/e2e/criticalFlow.spec.ts
```
