import { defineConfig, devices } from "@playwright/test";

// E2E da Central (backend-independente). Mock backend serve uma projection de hub com
// tiles → o app renderiza o launcher; + banner offline. Build com baseURL '/' (produção
// usa '/central/'). Fluxo com Django real (login efetivo, permissões) = reviewer local.
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3001",
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
      port: 3001,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        NUXT_APP_BASE_URL: "/",
        NUXT_DJANGO_BASE_URL: "http://127.0.0.1:8797",
        HOST: "127.0.0.1",
        PORT: "3001",
      },
    },
  ],
});
