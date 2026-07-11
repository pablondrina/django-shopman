import tailwindcss from "@tailwindcss/vite";
// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  // Superfície de operador: herda BFF/resiliência/telemetria/DS do kit compartilhado.
  extends: ["../operator-kit"],

  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    public: {
      djangoPublicBaseUrl:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    },
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
    // LIGHT-first — the Gestor is a counter/office surface (well-lit, manager-
    // facing), like the POS and unlike the KDS (dark, back-of-house). Dark stays
    // available via the toggle.
    preference: 'light',
    fallback: 'light',
    storageKey: 'orders-nuxt-color-mode',
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
    // Served at the subdomain root (gestor.…) → baseURL "/". Internal operator
    // surface; the public host lives only in the deploy spec, never hardcoded here.
    baseURL: process.env.NUXT_APP_BASE_URL || "/",
    head: {
      htmlAttrs: { lang: "pt-BR" },
      title: "Gestor de Pedidos",
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
        { name: "theme-color", content: "#ffffff" },
        { name: "robots", content: "noindex, nofollow" },
      ],
    },
  },

  vite: {
    plugins: [tailwindcss()]
  }
})
