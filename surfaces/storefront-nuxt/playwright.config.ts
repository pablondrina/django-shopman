import { defineConfig, devices } from '@playwright/test'

// E2E do storefront. Sobe um mock backend leve (respostas vazias rápidas) e o
// `nuxt preview` apontado a ele, para exercitar comportamentos do app que NÃO
// dependem de dados de negócio: shell degradado, guard de conta, banner offline,
// página 404. Fluxos com dados ricos (menu→carrinho→checkout) são specs marcados
// e rodam contra o Django real (reviewer local) — ver tests/e2e/README.
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.ts',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:3000',
    trace: 'retain-on-failure'
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } }
  ],
  webServer: [
    {
      command: 'node tests/e2e/mockBackend.mjs',
      port: 8799,
      reuseExistingServer: !process.env.CI
    },
    {
      // Serve o build de produção direto pelo Nitro (o `nuxt preview` malparseia
      // --host nesta versão). Exige `npm run build` antes.
      command: 'node .output/server/index.mjs',
      port: 3000,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        NUXT_DJANGO_BASE_URL: 'http://127.0.0.1:8799',
        HOST: '127.0.0.1',
        PORT: '3000'
      }
    }
  ]
})
