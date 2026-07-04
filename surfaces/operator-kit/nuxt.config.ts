// Nuxt layer compartilhado das superfícies de operador.
//
// Os apps (pos/orders/kds/production-nuxt + Central de Apps) fazem
// `extends: ['../operator-kit']` no seu nuxt.config. Este layer contribui:
//   - app/components  → auto-importados (ex.: OfflineBanner)
//   - app/composables → auto-importados (ex.: useConnectivity)
//   - app/utils       → auto-importados (ex.: retryWithBackoff, httpError, reportClientError)
//   - app/plugins     → registrados (ex.: errorReporter.client)
//
// Deliberadamente MÍNIMO: não impõe módulos, color-mode nem css ao app hospedeiro
// (cada app decide sua orientação — KDS dark-first, demais light-first — e importa o
// tailwind.css próprio). O que é genuinamente invariante e sem colisão de nome vive
// aqui; a de-duplicação dos arquivos byte-idênticos (djangoProxy/tw-helper/translucent)
// e a consolidação da família operator-lock acontecem nos WPs seguintes.
export default defineNuxtConfig({
  // Layer segue a convenção Nuxt 4 (srcDir `app/`) igual aos apps hospedeiros, para
  // que components/composables/utils/plugins em `app/` sejam auto-importados via extends.
  future: { compatibilityVersion: 4 },
});
