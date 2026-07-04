import { defineConfig } from "vitest/config";

// Testes do próprio kit: utils puros (resiliência/telemetria) + guardrails de design
// system (fs-based, leem os tailwind.css dos apps irmãos). Env node, sem Nuxt — rápido.
// Os apps que fazem `extends` deste layer têm sua própria suíte (2-projects).
export default defineConfig({
  test: {
    name: "operator-kit",
    environment: "node",
    globals: true,
    include: ["tests/**/*.test.ts"],
  },
});
