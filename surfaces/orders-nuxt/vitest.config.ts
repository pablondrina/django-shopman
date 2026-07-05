import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import { defineVitestProject } from "@nuxt/test-utils/config";

const appAlias = {
  "~": fileURLToPath(new URL("./app", import.meta.url)),
  "@": fileURLToPath(new URL("./app", import.meta.url)),
};

export default defineConfig({
  test: {
    projects: [
      // Unit: presentation pura, composables e BFF. Env `node` (transform plano, sem
      // auto-import do Nuxt — os composables injetam as fatias do framework como globais).
      // ⚠️ Os composables ficam AQUI (não no projeto `component`) porque orders tem
      // pages/ (router) e o @nuxt/test-utils 4.0.3 quebra o SETUP do env `nuxt` para apps
      // com router (`nuxtApp._route` undefined) — sem versão que corrija. Ver os testes.
      {
        resolve: { alias: appAlias },
        test: {
          name: "unit",
          environment: "node",
          globals: true,
          include: ["tests/**/*.test.ts"],
          exclude: ["tests/components/**", "tests/e2e/**", "node_modules/**"],
        },
      },
      // Component: monta componentes Vue reais (env `nuxt`/happy-dom). Reservado p/
      // B-ORD.6 — bloqueado pelo mesmo bug de router do test-utils; abordagem definida lá.
      await defineVitestProject({
        test: {
          name: "component",
          environment: "nuxt",
          globals: true,
          include: ["tests/components/**/*.test.ts"],
        },
      }),
    ],
  },
});
