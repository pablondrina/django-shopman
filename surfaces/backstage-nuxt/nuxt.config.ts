const isProduction = process.env.NODE_ENV === 'production'
const djangoBaseUrl = process.env.NUXT_DJANGO_BASE_URL || 'http://127.0.0.1:8000'
const posSurfaceUrl = process.env.NUXT_PUBLIC_POS_SURFACE_URL || (isProduction ? '/pos/' : 'http://127.0.0.1:3002/')

export default defineNuxtConfig({
  modules: ['@nuxt/ui'],
  compatibilityDate: '2026-05-09',
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    djangoBaseUrl,
    public: {
      posSurfaceUrl
    }
  },
  // Django paths (/admin, /gestor, /static) are proxied via explicit handlers
  // in server/routes/ so we control redirects and CSRF headers ourselves.
  app: {
    baseURL: process.env.NUXT_APP_BASE_URL || (isProduction ? '/backstage/' : '/'),
    head: {
      htmlAttrs: { lang: 'pt-BR' },
      title: 'Shopman Backstage',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'theme-color', content: '#0a0a0a' },
        { name: 'robots', content: 'noindex, nofollow' }
      ]
    }
  }
})
