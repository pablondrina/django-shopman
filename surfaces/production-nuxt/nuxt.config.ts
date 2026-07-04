import tailwindcss from "@tailwindcss/vite";
// https://nuxt.com/docs/api/configuration/nuxt-config
const isProduction = process.env.NODE_ENV === "production";

export default defineNuxtConfig({
  compatibilityDate: "2026-05-16",
  devtools: { enabled: false },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    public: {
      djangoPublicBaseUrl:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
      operatorLoginNextPath: process.env.NUXT_PRODUCTION_LOGIN_NEXT_PATH || (isProduction ? "/" : "/admin/"),
    },
  },

  modules: [
    '@nuxtjs/color-mode',
    'motion-v/nuxt',
    '@vueuse/nuxt',
    '@nuxt/icon',
    '@nuxt/fonts',
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
    // LIGHT-first — the production app is touch-first but light (Pablo's call),
    // like the Gestor and unlike the KDS (dark, back-of-house). Dark stays
    // available via the toggle for the back-of-house bakery floor.
    preference: 'light',
    fallback: 'light',
    storageKey: 'production-nuxt-color-mode',
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
    // Served at the subdomain root (fournil.…) → baseURL "/". Internal operator
    // surface; the public host lives only in the deploy spec, never hardcoded here.
    baseURL: process.env.NUXT_APP_BASE_URL || "/",
    head: {
      htmlAttrs: { lang: "pt-BR" },
      title: "Produção",
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
        { name: "theme-color", content: "#ffffff" },
        { name: "robots", content: "noindex, nofollow" },
      ],
    },
  },

  vite: {
    plugins: [tailwindcss()],
    server: {
      // Dev-only: permite espiar o dev server por um quick tunnel do
      // Cloudflare (QA remoto antes de publicar). Produção não passa por
      // aqui (build Nitro, sem dev server).
      allowedHosts: isProduction ? [] : [".trycloudflare.com"],
    },
  }
})
