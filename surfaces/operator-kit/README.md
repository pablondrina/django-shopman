# operator-kit — Nuxt layer compartilhado das superfícies de operador

Fundação comum das superfícies de operador (`pos-nuxt`, `orders-nuxt`, `kds-nuxt`,
`production-nuxt`) e da central **Central de Apps** (`hub-nuxt`). Mata o copy-paste que
a auditoria encontrou (BFF/resiliência/DS byte-idênticos duplicados nos 4 apps).

O **storefront-nuxt fica de fora** (superfície de cliente, branded, harness próprio).

## Como um app consome

No `nuxt.config.ts` do app:

```ts
export default defineNuxtConfig({
  extends: ["../operator-kit"],
  // ... config do app (color-mode, css, app.head, etc.)
});
```

O layer contribui, via auto-import do Nuxt:

| Área | Símbolo | Papel |
|---|---|---|
| `app/utils/httpError.ts` | `httpError`, `isTransientError` | narrowing tipado de erro de rede |
| `app/utils/retryBackoff.ts` | `retryWithBackoff` | backoff exponencial + jitter + teto |
| `app/utils/clientErrorReport.ts` | `reportClientError`, `buildClientErrorReport` | telemetria → `backstage/client-error/` |
| `app/composables/useConnectivity.ts` | `useConnectivity` | sinal offline + reconciliação no reconnect/foco |
| `app/components/OfflineBanner.vue` | `<OfflineBanner>` | aviso calmo de conexão (colocar no layout raiz) |
| `app/plugins/errorReporter.client.ts` | — | captura erro não-tratado → telemetria (inerte em dev) |

## O que ainda NÃO vive aqui (roadmap — ver docs/plans/BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md)

- **De-duplicação dos byte-idênticos** `server/utils/djangoProxy.ts`, `app/utils/tw-helper.ts`,
  `app/utils/translucent.ts` — migram para cá com atualização dos imports/testes dos apps.
- **Família operator-lock** (`useOperatorLock`, `OperatorLock/Login/PinChange`,
  `operatorSession`) — hoje DIVERGE entre os apps (2–3 variantes; POS tem tela própria);
  consolidar num canônico é trabalho dos WPs por-app.
- **DS tokens canônicos** (`tailwind.css`) — hoje idênticos por app; extrair o bloco
  canônico para cá (com split das partes app-específicas: print no POS, dark no KDS).
- **Interceptor global de 401/403** (reabre o gate de operador) — plugin compartilhado.
- **Tooling base** (ESLint flat + Prettier + vitest 2-projects + Playwright) — configs
  compartilhadas adotadas por cada app no seu WP.

## Testes do kit

```bash
npm test   # vitest: utils puros + guardrails de design system (paridade de tokens)
```

Os guardrails (`tests/guardrails.test.ts`) leem os `tailwind.css` dos 4 apps e falham
se um token canônico divergir — travam a drift do design system (Lente 7 do plano).
