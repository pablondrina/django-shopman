import tailwindcss from "@tailwindcss/vite";
// https://nuxt.com/docs/api/configuration/nuxt-config
const isProduction = process.env.NODE_ENV === "production";

export default defineNuxtConfig({
  // Superfície de operador: herda BFF/resiliência/telemetria/DS do kit compartilhado.
  extends: ["../operator-kit"],

  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
  },

  // 301 das rotas antigas → enxutas: estação direta em /<ref> (era /estacao/<ref>);
  // board do cliente em /retirada (era /cliente). Splat preservado pelo Nitro.
  routeRules: {
    "/estacao/**": { redirect: { to: "/**", statusCode: 301 } },
    "/cliente": { redirect: { to: "/retirada", statusCode: 301 } },
  },

  modules: [
    '@nuxtjs/color-mode',
    'motion-v/nuxt',
    '@vueuse/nuxt',
    '@nuxt/icon',
    '@nuxt/fonts',
    '@nuxt/eslint',
    "vue-sonner/nuxt"
  ],

  imports: {
    imports: [{
      from: 'tailwind-variants',
      name: 'tv'
    }, {
      from: 'tailwind-variants',
      name: 'VariantProps',
      type: true
    }, {
      from: "vue-sonner",
      name: "toast",
      as: "useSonner"
    }]
  },

  colorMode: {
    // DARK-first — KDS best practice (back-of-house: low light, less eye strain,
    // the time semaphore pops on dark). Diverges from the POS (light, counter-
    // facing) on purpose; light stays available via the toggle.
    preference: 'dark',
    fallback: 'dark',
    storageKey: 'kds-nuxt-color-mode',
    classSuffix: ''
  },

  icon: {
    clientBundle: {
      scan: true,
      sizeLimitKb: 0
    },

    mode: 'svg',
    class: 'shrink-0',
    fetchTimeout: 2000,
    serverBundle: 'local'
  },

  css: ["~/assets/css/tailwind.css"],

  app: {
    baseURL: process.env.NUXT_APP_BASE_URL || (isProduction ? "/kds/" : "/"),
    head: {
      htmlAttrs: { lang: "pt-BR" },
      title: "Shopman KDS",
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
        { name: "theme-color", content: "#0a0a0a" },
        { name: "robots", content: "noindex, nofollow" },
      ],
    },
  },

  vite: {
    plugins: [tailwindcss()]
  }
})