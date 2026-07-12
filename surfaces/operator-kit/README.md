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
| `app/types/operator.ts` | `OperatorCard`, `OperatorSession`, … | espelho TS da API operator/session\|eligible\|unlock\|lock |
| `app/presentation/operatorLock.ts` | `isLocked`, `buildUnlockPayload`, … | transforms puros do lock (sem I/O) |
| `app/composables/useOperatorLock.ts` | `useOperatorLock` | read/write do lock de operador (PIN/crachá) via proxy |
| `app/components/OperatorLock.vue` | `<OperatorLock>` | overlay de lock (picker + PIN pad + crachá + troca forçada) |
| `app/components/OperatorPinChange.vue` | `<OperatorPinChange>` | numpad de troca de PIN (forçada e voluntária) |

## O que ainda NÃO vive aqui (roadmap — ver docs/plans/completed/BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md)

- **De-duplicação dos byte-idênticos** `server/utils/djangoProxy.ts`, `app/utils/tw-helper.ts`,
  `app/utils/translucent.ts` — migram para cá com atualização dos imports/testes dos apps.
- **Lock do POS** — o POS mantém deliberadamente a própria variante
  (`usePosOperatorLock` + `PosLockScreen`/`PosPinChange`): auto-lock por inatividade,
  transporte via `usePosAction` e lock local-first. A família canônica
  (`useOperatorLock`/`OperatorLock`/`OperatorPinChange`) vive aqui e serve
  kds/orders/production.
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
