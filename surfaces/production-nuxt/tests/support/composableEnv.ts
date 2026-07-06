import { vi } from "vitest";
import { computed, nextTick, reactive, readonly, ref, shallowRef, watch } from "vue";

// Utilitários REAIS do operator-kit (auto-imports em runtime) — injetamos a implementação
// verdadeira (não um mock) para o teste exercitar o narrowing/mensagem de fato (os `catch`
// dos composables usam httpError/httpErrorMessage do kit — WP .4).
import { httpError, httpErrorMessage } from "../../../operator-kit/app/utils/httpError";

/**
 * Harness ÚNICO para testar os composables do Fournil em env `node`.
 *
 * Por que node e não o env `nuxt`: o `@nuxt/test-utils` 4.0.3 (última versão) quebra no
 * SETUP para apps COM router/pages — `nuxtApp._route` fica undefined e o ambiente nem
 * inicia. production-nuxt tem `pages/`. Mesma correção provada em orders-nuxt (B-ORD.1).
 *
 * Por que NÃO é gambiarra: a REATIVIDADE é o Vue REAL — `computed`/`ref`/`reactive`/`watch`
 * são as implementações verdadeiras, então os derivados recomputam de fato. Só a
 * **fronteira de dados/framework** é mockada (`useFetch`/`$fetch`/`useSonner`/config e os
 * auto-imports do app: `operatorSessionOnError`, `useAdaptivePoll`, `refreshNuxtData`) —
 * exatamente o que se mocka em QUALQUER teste unitário desses composables. Lifecycle
 * (onMounted/onBeforeUnmount/onUnmounted) vira no-op: poll/timers são território de e2e e
 * de testes dedicados (useAdaptivePoll tem o seu próprio, dirigindo o ciclo à mão).
 *
 * Se um composable passar a usar um auto-import não previsto aqui, o teste falha ALTO
 * (ReferenceError), nunca silenciosamente errado — então o harness é auto-revelador.
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
  /** `refreshNuxtData` (usado pelo unlock e pelo operatorSessionOnError). */
  refreshNuxtData: ReturnType<typeof vi.fn>;
  /** `useAdaptivePoll` — no-op observável (o poll de verdade é testado à parte). */
  adaptivePoll: ReturnType<typeof vi.fn>;
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
    adaptivePoll: vi.fn(),
    runtimeConfig: { public: { djangoPublicBaseUrl: "" } },
    reset() {
      env.fetchData.value = null;
      env.refresh.mockReset();
      env.fetchMock.mockReset().mockResolvedValue({});
      env.sonner.error.mockReset();
      env.sonner.success.mockReset();
      env.refreshNuxtData.mockReset();
      env.adaptivePoll.mockReset();
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
  vi.stubGlobal("operatorSessionOnError", () => {});
  vi.stubGlobal("useAdaptivePoll", env.adaptivePoll);
  vi.stubGlobal("httpError", httpError); // implementação REAL do kit (narrowing tipado)
  vi.stubGlobal("httpErrorMessage", httpErrorMessage); // implementação REAL do kit
  vi.stubGlobal("useFetch", () => ({
    data: ref(env.fetchData.value),
    pending: ref(false),
    error: ref(null),
    refresh: env.refresh,
  }));
  vi.stubGlobal("$fetch", env.fetchMock);

  return env;
}
