import { defineConfig, devices } from "@playwright/test";

// E2E do Fournil (backend-independente). O mock backend serve uma sessão autenticada + um
// board de produção → as telas de operador renderizam; + o painel público (menuboard, sem
// auth) e os estados vazio/erro. Build com baseURL '/' (produção usa '/'). Login efetivo,
// lock (Opção C) e ações reais rodam contra o Django real (reviewer local) — ver
// tests/e2e/README.
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    // Porta de e2e dedicada (3105), distinta do dev server (3005) — o build de produção do
    // e2e sobe aqui e aponta ao mock, sem colidir/reusar um dev server aberto em :3005.
    baseURL: "http://127.0.0.1:3105",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/e2e/mockBackend.mjs",
      port: 8797,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "nuxt build && node .output/server/index.mjs",
      port: 3105,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:8797",
        HOST: "127.0.0.1",
        PORT: "3105",
      },
    },
  ],
});
