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
      // Unit: presentation pura, composables (com $fetch mockado) e BFF. Env `node`.
      {
        resolve: { alias: appAlias },
        test: {
          name: "unit",
          environment: "node",
          globals: true,
          include: ["tests/**/*.test.ts"],
          exclude: ["tests/components/**", "tests/composables/**", "tests/e2e/**", "node_modules/**"],
        },
      },
      // Component: monta componentes Vue reais com auto-imports/composables do Nuxt
      // (mountSuspended). Env `nuxt` (happy-dom) — mais pesado, isolado aqui.
      await defineVitestProject({
        test: {
          name: "component",
          environment: "nuxt",
          globals: true,
          include: ["tests/components/**/*.test.ts", "tests/composables/**/*.test.ts"],
        },
      }),
    ],
  },
});
