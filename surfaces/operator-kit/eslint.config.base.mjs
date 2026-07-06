// Base flat-config compartilhada das superfícies de operador. Cada app faz:
//
//   import withNuxt from './.nuxt/eslint.config.mjs'
//   import operatorKit from '../operator-kit/eslint.config.base.mjs'
//   import prettier from 'eslint-config-prettier'
//   export default withNuxt(...operatorKit, prettier)
//
// `@nuxt/eslint` gera `.nuxt/eslint.config.mjs` no `nuxt prepare`; estes objetos só
// ajustam regras. Mantém a mesma disciplina do storefront: `any` é LOUD no código de
// app (dívida a zerar), tolerado em test doubles e nas primitivas vendadas `Ui/**`.
export default [
  {
    ignores: ["**/.nuxt/**", "**/.output/**", "**/dist/**", "**/node_modules/**", "**/public/**", "tests/e2e/**"],
  },
  {
    rules: {
      // Reka-UI/ui-thing: props opcionais sem default são intencionais (o componente
      // decide o fallback via tv/reka). Regra gera 150+ falsos positivos em UI libs.
      "vue/require-default-prop": "off",
      "vue/multi-word-component-names": "off",
      // `any` fica visível de propósito: é a dívida de type-safety que o WP .4 zera.
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  {
    // Test doubles legitimamente usam `any` (mocks de $fetch, casts `as never`).
    files: ["tests/**/*.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    // Primitivas de UI vendadas (ui-thing/reka-ui): a superfície pública da lib usa
    // `any`/passthrough por design; não é código nosso a re-tipar.
    files: ["app/components/Ui/**/*.vue"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-empty-object-type": "off",
      "vue/no-v-html": "off",
    },
  },
];
