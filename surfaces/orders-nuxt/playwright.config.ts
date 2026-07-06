import { defineConfig, devices } from "@playwright/test";

// E2E do Gestor (backend-independente). Mock backend serve uma sessão autenticada + uma
// fila com cards → o board renderiza; + banner offline. Build com baseURL '/' (produção
// usa '/gestor/'). Login efetivo, lock (Opção C) e ações reais rodam contra o Django real
// (reviewer local) — ver tests/e2e/README.
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3004",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/e2e/mockBackend.mjs",
      port: 8796,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "nuxt build && node .output/server/index.mjs",
      port: 3004,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:8796",
        HOST: "127.0.0.1",
        PORT: "3004",
      },
    },
  ],
});
