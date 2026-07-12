// Side-effect setup: instala os auto-imports do Nuxt como globais ANTES de qualquer import
// de composable. Necessário para composables SINGLETON que chamem `ref()` no ESCOPO DO
// MÓDULO (ex.: useOvenTimers/useFlapClack no production-nuxt) — o `ref` global precisa
// existir no instante em que o módulo avalia. Importe ESTE módulo primeiro:
//
//   import "../../../operator-kit/tests/support/installGlobals";
//   import { useX } from "~/composables/useX";
//
// (ESM avalia os imports em ordem de origem, então este roda antes do módulo singleton.)
import { installNuxtGlobals } from "./composableEnv";

installNuxtGlobals();
