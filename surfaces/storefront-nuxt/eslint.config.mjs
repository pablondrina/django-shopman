// Flat config: parte do preset do Nuxt (@nuxt/eslint gera .nuxt/eslint.config.mjs
// no `nuxt prepare`) e desliga regras de estilo que conflitam com o Prettier.
import withNuxt from './.nuxt/eslint.config.mjs'
import prettier from 'eslint-config-prettier'

export default withNuxt(
  {
    ignores: [
      '.nuxt/**',
      '.output/**',
      'dist/**',
      'node_modules/**',
      'public/**',
      'tests/e2e/**'
    ]
  },
  {
    rules: {
      // Design-system Reka-UI: props opcionais sem default são intencionais (o
      // componente decide o fallback via `tv`/reka). A regra gera 150+ falsos
      // positivos sem valor — padrão do ecossistema é desligá-la em UI libs.
      'vue/require-default-prop': 'off',
      'vue/multi-word-component-names': 'off',
      // `any` fica LOUD de propósito: é a dívida de type-safety que o WP-S4 zera
      // (catch tipado, normalizações defensivas → `unknown` + type guards).
      '@typescript-eslint/no-explicit-any': 'error'
    }
  },
  {
    // Test doubles legitimamente usam `any` (mocks de $fetch, casts `as never`).
    // O alvo do no-explicit-any é o código de app, não a instrumentação de teste.
    files: ['tests/**/*.ts'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off'
    }
  },
  {
    // Primitivas de UI vendadas (ui-thing/reka-ui): `class?: any`, `customData?:
    // any`, `[key: string]: any` são a superfície pública da lib, não código nosso
    // a re-tipar. O alvo de type-safety é a nossa lógica (composables/páginas/
    // presentation), coberta pela regra global.
    files: ['app/components/Ui/**/*.vue'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      // Primitivas com passthrough de conteúdo (ex.: Card content) usam v-html
      // por design da lib; o conteúdo é responsabilidade do call-site.
      'vue/no-v-html': 'off'
    }
  },
  prettier
)
