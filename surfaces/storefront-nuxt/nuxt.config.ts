export default defineNuxtConfig({
  modules: ['@nuxt/ui'],
  compatibilityDate: '2026-05-07',
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || 'http://127.0.0.1:8000'
  },
  app: {
    baseURL: process.env.NUXT_APP_BASE_URL || (process.env.NODE_ENV === 'production' ? '/nuxt/' : '/'),
    head: {
      htmlAttrs: { lang: 'pt-BR' },
      title: 'Shopman Nuxt',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'theme-color', content: '#fafaf9' }
      ]
    }
  }
})
