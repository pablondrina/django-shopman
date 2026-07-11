import { vi } from "vitest";
import { computed, nextTick, reactive, readonly, ref, shallowRef, watch } from "vue";

/**
 * Harness para testar composables do kit em env `node` (mesma abordagem provada nos
 * apps consumidores): a REATIVIDADE é o Vue REAL — `computed`/`ref`/`reactive`/`watch`
 * são as implementações verdadeiras, então os derivados recomputam de fato. Só a
 * **fronteira de dados/framework** é mockada (`useFetch`/`$fetch`/`useSonner`/config e
 * `refreshNuxtData`). Lifecycle (onMounted/onBeforeUnmount/onUnmounted) vira no-op.
 *
 * Se um composable passar a usar um auto-import não previsto aqui, o teste falha ALTO
 * (ReferenceError), nunca silenciosamente errado — o harness é auto-revelador.
 */
export interface ComposableEnv {
  /** Payload que o `useFetch` mockado devolve (definir ANTES de chamar o composable). */
  fetchData: { value: unknown };
  /** `refresh` do useFetch. */
  refresh: ReturnType<typeof vi.fn>;
  /** `$fetch` (transporte de ação/escrita). */
  fetchMock: ReturnType<typeof vi.fn>;
  /** `useSonner` (toast). */
  sonner: { error: ReturnType<typeof vi.fn>; success: ReturnType<typeof vi.fn> };
  /** `refreshNuxtData` (usado pelo unlock: recarrega os fetches que rodaram trancados). */
  refreshNuxtData: ReturnType<typeof vi.fn>;
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
    refreshNuxtData: vi.fn(),
    runtimeConfig: { app: { baseURL: "/" }, public: {} },
    reset() {
      env.fetchData.value = null;
      env.refresh.mockReset();
      env.fetchMock.mockReset().mockResolvedValue({});
      env.sonner.error.mockReset();
      env.sonner.success.mockReset();
      env.refreshNuxtData.mockReset();
    },
  };

  // Reatividade REAL do Vue.
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("reactive", reactive);
  vi.stubGlobal("readonly", readonly);
  vi.stubGlobal("shallowRef", shallowRef);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("nextTick", nextTick);
  // Lifecycle: sem componente montado → no-op.
  vi.stubGlobal("onMounted", () => {});
  vi.stubGlobal("onBeforeUnmount", () => {});
  vi.stubGlobal("onUnmounted", () => {});
  vi.stubGlobal("onScopeDispose", () => {});
  // Fronteira de dados/framework — mockada.
  vi.stubGlobal("useRuntimeConfig", () => env.runtimeConfig);
  vi.stubGlobal("useSonner", env.sonner);
  vi.stubGlobal("refreshNuxtData", env.refreshNuxtData);
  vi.stubGlobal("useFetch", () => ({
    data: ref(env.fetchData.value),
    pending: ref(false),
    error: ref(null),
    refresh: env.refresh,
  }));
  vi.stubGlobal("$fetch", env.fetchMock);

  return env;
}
