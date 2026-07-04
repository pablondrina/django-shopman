import tailwindcss from "@tailwindcss/vite";
// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2026-05-16',
  devtools: { enabled: false },

  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || 'http://127.0.0.1:8000'
  },

  // 301 das rotas antigas (inglês) → pt-BR. Rede de segurança para links já enviados
  // (notificações/WhatsApp), bookmarks e qualquer href interno que escape. Query e
  // splat (**) são preservados pelo Nitro.
  routeRules: {
    '/cart': { redirect: { to: '/sacola', statusCode: 301 } },
    '/checkout': { redirect: { to: '/finalizar', statusCode: 301 } },
    '/login': { redirect: { to: '/entrar', statusCode: 301 } },
    '/account': { redirect: { to: '/conta', statusCode: 301 } },
    '/account/**': { redirect: { to: '/conta/**', statusCode: 301 } },
    '/product/**': { redirect: { to: '/produto/**', statusCode: 301 } },
    '/tracking/**': { redirect: { to: '/pedido/**', statusCode: 301 } },
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

  // Tipografia canônica self-hospedada via @nuxt/fonts (baixa, self-hospeda e injeta
  // @font-face + métrica de fallback size-adjust = zero CLS):
  //  · Instrument Sans → corpo (--font-sans canônica; 500 incluso p/ o chrome das
  //    primitivas Ui). É a fonte oficial do tema, não mais um <link> de runtime da marca.
  //  · Fraunces (serif, eixo opsz) → títulos (.shop-display/.shop-title), com
  //    font-optical-sizing: auto dando o corte display nos títulos grandes.
  fonts: {
    families: [
      { name: 'Instrument Sans', provider: 'google', weights: [400, 500, 600], styles: ['normal'] },
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
    storageKey: 'storefront-nuxt-color-mode',
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
