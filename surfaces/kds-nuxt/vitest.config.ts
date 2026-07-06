import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const appAlias = {
  "~": fileURLToPath(new URL("./app", import.meta.url)),
  "@": fileURLToPath(new URL("./app", import.meta.url)),
};

// ⚠️ kds-nuxt tem pages/ (router) e o env `nuxt` do @nuxt/test-utils 4.0.3 quebra no SETUP
// para apps com router (`nuxtApp._route` undefined). Mesma correção provada em orders/
// production. Dois projetos SEM env nuxt:
//   - unit (node): presentation, composables (auto-imports do Nuxt injetados como globais
//     no harness) e BFF. Ver tests/support/composableEnv.ts.
//   - component (happy-dom + @vitejs/plugin-vue): monta SFCs reais com @vue/test-utils,
//     SEM o runtime Nuxt — Icon/NuxtLink viram stubs; auto-imports viram globais.
export default defineConfig({
  test: {
    projects: [
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
      {
        plugins: [vue()],
        resolve: { alias: appAlias },
        test: {
          name: "component",
          environment: "happy-dom",
          globals: true,
          include: ["tests/components/**/*.test.ts"],
        },
      },
    ],
  },
});
