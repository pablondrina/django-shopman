import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const appAlias = {
  "~": fileURLToPath(new URL("./app", import.meta.url)),
  "@": fileURLToPath(new URL("./app", import.meta.url)),
};

// ⚠️ orders-nuxt tem pages/ (router) e o env `nuxt` do @nuxt/test-utils 4.0.3 quebra no
// SETUP para apps com router. Por isso:
//   - unit (node): presentation, composables (auto-imports do Nuxt injetados como globais
//     no harness) e BFF. Harness compartilhado: operator-kit/tests/support/composableEnv.ts.
//   - component (happy-dom + @vitejs/plugin-vue): monta SFCs reais com @vue/test-utils,
//     SEM o runtime Nuxt — Icon/NuxtLink viram stubs; computed/useNowTick viram globais.
export default defineConfig({
  test: {
    projects: [
      {
        // dedupe("vue"): o harness compartilhado vive na operator-kit e importa "vue" de lá;
        // sem dedupe seriam DUAS instâncias do Vue no mesmo processo (refs criadas pelo
        // teste não rastreariam em watch/computed do harness).
        resolve: { alias: appAlias, dedupe: ["vue"] },
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
