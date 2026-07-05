import { defineConfig } from "vitest/config";
import { defineVitestProject } from "@nuxt/test-utils/config";

// Suíte do próprio kit — mesma estrutura 2-projects dos apps que fazem `extends`:
//   - unit (env node): utils puros (resiliência/telemetria) + guardrails de design
//     system (fs-based, leem os tailwind.css dos apps irmãos). Rápido, sem runtime.
//   - component (env nuxt): composables/componentes que dependem do runtime Nuxt
//     (useState, auto-imports, @vueuse, DOM) — testados NA FONTE, não por um consumidor
//     downstream (era a dívida: useOperatorSession/useConnectivity só rodavam no POS).
export default defineConfig({
  test: {
    projects: [
      {
        test: {
          name: "operator-kit",
          environment: "node",
          globals: true,
          include: ["tests/**/*.test.ts"],
          exclude: ["tests/composables/**", "tests/components/**", "node_modules/**"],
        },
      },
      await defineVitestProject({
        test: {
          name: "operator-kit:nuxt",
          environment: "nuxt",
          globals: true,
          include: ["tests/composables/**/*.test.ts", "tests/components/**/*.test.ts"],
        },
      }),
    ],
  },
});
