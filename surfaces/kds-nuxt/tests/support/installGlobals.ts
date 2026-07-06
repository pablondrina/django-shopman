// Side-effect setup: instala os auto-imports do Nuxt como globais ANTES de qualquer import
// de composable. Necessário para composables SINGLETON que chamem `ref()` no ESCOPO DO
// MÓDULO (o `ref` global precisa existir quando o módulo avalia). Importe ESTE módulo
// primeiro:
//
//   import "../support/installGlobals";
//   import { useX } from "~/composables/useX";
//
// (ESM avalia os imports em ordem de origem, então este roda antes do módulo do composable.)
import { installNuxtGlobals } from "./composableEnv";

installNuxtGlobals();
