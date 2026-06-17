import tailwindcss from "@tailwindcss/vite";
// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2026-05-16',
  devtools: { enabled: false },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || 'http://127.0.0.1:8000'
  },

  app: {
    baseURL: process.env.NUXT_APP_BASE_URL || '/',
    head: {
      htmlAttrs: { lang: 'pt-BR' },
      titleTemplate: title => title ? `${title} | Shopman` : 'Shopman',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'theme-color', content: '#85786c' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'default' }
      ]
    }
  },

  modules: [
    '@nuxtjs/color-mode',
    'motion-v/nuxt',
    '@vueuse/nuxt',
    '@nuxt/icon',
    '@nuxt/fonts',
    "@yuta-inoue-ph/nuxt-vcalendar",
    "vue-sonner/nuxt"
  ],

  // Display serif (Fraunces) self-hospedada para os títulos — corpo segue system-ui.
  // @nuxt/fonts baixa, self-hospeda e injeta @font-face + métrica de fallback
  // (size-adjust) p/ zero CLS. Variável c/ eixo opsz: font-optical-sizing: auto
  // dá o corte display automático nos títulos grandes.
  fonts: {
    families: [
      { name: 'Fraunces', provider: 'google', weights: [400, 600], styles: ['normal'] }
    ]
  },

  imports: {
    imports: [{
      from: 'tailwind-variants',
      name: 'tv'
    }, {
      from: 'tailwind-variants',
      name: 'VariantProps',
      type: true
    }, {
      from: 'vue-sonner',
      name: 'toast',
      as: 'useSonner'
    }]
  },

  colorMode: {
    storageKey: 'storefront-uithing-nuxt-color-mode',
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

  css: ['~/assets/css/tailwind.css'],

  vite: {
    plugins: [tailwindcss()],
    optimizeDeps: {
      include: ['reka-ui', 'tailwind-variants', 'v-calendar']
    }
  }
})
