import { vi } from "vitest";
import { computed, reactive, ref, watch } from "vue";

/**
 * Harness ÚNICO para testar os composables do Gestor em env `node`.
 *
 * Por que node e não o env `nuxt`: o `@nuxt/test-utils` 4.0.3 (última versão) quebra no
 * SETUP para apps COM router/pages — `nuxtApp._route` fica undefined e o ambiente nem
 * inicia. orders-nuxt tem `pages/`. Sem correção upstream (ver B-ORD.1).
 *
 * Por que NÃO é gambiarra: a REATIVIDADE é o Vue REAL — `computed`/`ref`/`reactive`/`watch`
 * são as implementações verdadeiras, então os derivados recomputam de fato. Só a
 * **fronteira de dados/framework** é mockada (`useFetch`/`$fetch`/`useSonner`/config) —
 * exatamente o que se mocka em QUALQUER teste unitário desse composable, inclusive no env
 * `nuxt` (lá seria `mockNuxtImport`, aqui é `vi.stubGlobal`; mesma fronteira, outro
 * mecanismo). Lifecycle (onMounted/onBeforeUnmount) vira no-op: poll/SSE/timers são
 * território de e2e, não de teste unitário do write-side.
 *
 * Se um composable passar a usar um auto-import não previsto aqui, o teste falha ALTO
 * (ReferenceError), nunca silenciosamente errado — então o harness é auto-revelador.
 */
export interface ComposableEnv {
  /** Payload que o `useFetch` mockado devolve (definir ANTES de chamar o composable). */
  fetchData: { value: unknown };
  /** `refresh` do useFetch. */
  refresh: ReturnType<typeof vi.fn>;
  /** `$fetch` (transporte de ação). */
  fetchMock: ReturnType<typeof vi.fn>;
  /** `useSonner` (toast). */
  sonner: { error: ReturnType<typeof vi.fn>; success: ReturnType<typeof vi.fn> };
  /** `useRuntimeConfig()`. */
  runtimeConfig: Record<string, unknown>;
  /** Zera histórico dos mocks e o payload (chamar no `beforeEach`). */
  reset(): void;
}

export function installNuxtGlobals(): ComposableEnv {
  const env: ComposableEnv = {
    fetchData: { value: null },
    refresh: vi.fn(),
    fetchMock: vi.fn(),
    sonner: { error: vi.fn(), success: vi.fn() },
    runtimeConfig: { public: { djangoPublicBaseUrl: "" } },
    reset() {
      env.fetchData.value = null;
      env.refresh.mockReset();
      env.fetchMock.mockReset().mockResolvedValue({});
      env.sonner.error.mockReset();
      env.sonner.success.mockReset();
    },
  };

  // Reatividade REAL do Vue.
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("reactive", reactive);
  vi.stubGlobal("watch", watch);
  // Lifecycle: sem componente montado → no-op.
  vi.stubGlobal("onMounted", () => {});
  vi.stubGlobal("onBeforeUnmount", () => {});
  vi.stubGlobal("onScopeDispose", () => {});
  // Fronteira de dados/framework — mockada.
  vi.stubGlobal("useRuntimeConfig", () => env.runtimeConfig);
  vi.stubGlobal("useSonner", env.sonner);
  vi.stubGlobal("operatorSessionOnError", () => {});
  vi.stubGlobal("useFetch", () => ({
    data: ref(env.fetchData.value),
    pending: ref(false),
    error: ref(null),
    refresh: env.refresh,
  }));
  vi.stubGlobal("$fetch", env.fetchMock);

  return env;
}
