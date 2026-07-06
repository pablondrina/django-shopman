// Side-effect setup: instala os auto-imports do Nuxt como globais ANTES de qualquer
// import de composable. Necessário para os composables SINGLETON (useOvenTimers/
// useFlapClack), que chamam `ref()` no ESCOPO DO MÓDULO — o `ref` global precisa existir
// no instante em que o módulo avalia. Importe ESTE módulo primeiro:
//
//   import "../support/installGlobals";
//   import { useOvenTimers } from "~/composables/useOvenTimers";
//
// (ESM avalia os imports em ordem de origem, então este roda antes do módulo singleton.)
import { installNuxtGlobals } from "./composableEnv";

installNuxtGlobals();
