// Nuxt layer compartilhado das superfícies de operador.
//
// Os apps (pos/orders/kds/production-nuxt + Central de Apps) fazem
// `extends: ['../operator-kit']` no seu nuxt.config. Este layer contribui:
//   - app/components  → auto-importados (ex.: OfflineBanner)
//   - app/composables → auto-importados (ex.: useConnectivity)
//   - app/utils       → auto-importados (ex.: retryWithBackoff, httpError, tw, translucent)
//   - app/plugins     → registrados (ex.: errorReporter.client)
//   - server/utils    → auto-importados pelo Nitro (djangoProxy, eventStream, apiVersion)
//
// Deliberadamente MÍNIMO: não impõe módulos, color-mode nem css ao app hospedeiro
// (cada app decide sua orientação — KDS dark-first, demais light-first — e importa o
// tailwind.css próprio). O que é genuinamente invariante e sem colisão de nome vive
// aqui; a família operator-lock canônica (types/presentation/composable/overlay) vive
// neste layer (o POS mantém a própria variante, usePosOperatorLock). O storefront fica
// de fora (superfície de cliente, branded, proxy e harness próprios).
export default defineNuxtConfig({
  // Layer segue a convenção Nuxt 4 (srcDir `app/`) igual aos apps hospedeiros, para
  // que components/composables/utils/plugins em `app/` sejam auto-importados via extends.
  future: { compatibilityVersion: 4 },

  runtimeConfig: {
    public: {
      // URL da Central de Apps (launcher) — o ícone do app no topo do OperatorRail leva
      // pra cá (padrão Odoo). Dev: hub-nuxt em :3001; prod: central.<zona> via env.
      operatorHubUrl: process.env.NUXT_PUBLIC_OPERATOR_HUB_URL || "http://127.0.0.1:3001/",
      // Estado inicial do rail (só quando não há cookie ainda). Padrão compacto; a própria
      // Central sobrescreve pra "collapsed" (é a casa, não precisa do rail aberto).
      railDefaultState: process.env.NUXT_PUBLIC_RAIL_DEFAULT_STATE || "compact",
    },
  },
});
