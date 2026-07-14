import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, ref } from "vue";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";

import type { OperatorCard } from "~/utils/operatorLock";

// Estado do lock de operador do POS. A fonte da verdade de auth (sessão/elegíveis/
// operador ativo) vem do lock compartilhado (operator-kit `useOperatorLock`), que
// mockamos; o transporte de unlock/lock/changePin (usePosAction) também. Exercemos
// os ramos de sucesso/erro das gravações — o caminho de risco não-testado — e que
// cada gravação reconcilia a sessão compartilhada (refresh).
const { callMock, refreshMock } = vi.hoisted(() => ({
  callMock: vi.fn(),
  refreshMock: vi.fn(),
}));
mockNuxtImport("usePosAction", () => () => ({ call: callMock }));
mockNuxtImport("useOperatorLock", () => () => ({
  authenticated: ref(true),
  locked: ref(true),
  operator: ref<OperatorCard | null>(null),
  mustChange: ref(false),
  eligible: ref<OperatorCard[]>([]),
  loadEligible: vi.fn(),
  refresh: refreshMock,
}));

// Monta um componente mínimo para o composable ter contexto de lifecycle (onMounted/
// onBeforeUnmount registram listeners de idle).
function withSetup<T>(composable: () => T): { result: T; unmount: () => void } {
  let result!: T;
  const app = createApp({
    setup() {
      result = composable();
      return () => null;
    },
  });
  app.mount(document.createElement("div"));
  return { result, unmount: () => app.unmount() };
}

const ana: OperatorCard = { id: 1, username: "ana", name: "Ana" };

describe("usePosOperatorLock", () => {
  beforeEach(() => {
    callMock.mockReset();
    refreshMock.mockReset();
  });

  it("unlock com sucesso reconcilia a sessão compartilhada e não deixa erro", async () => {
    callMock.mockResolvedValue({ ok: true, operator: ana });
    const { result, unmount } = withSetup(() => usePosOperatorLock({}));
    await expect(result.unlock(1, "1234")).resolves.toBe(true);
    expect(refreshMock).toHaveBeenCalledOnce();
    expect(result.error.value).toBe("");
    unmount();
  });

  it("unlock com ok:false expõe a mensagem do servidor e NÃO reconcilia", async () => {
    callMock.mockResolvedValue({ ok: false, error: { message: "PIN incorreto" } });
    const { result, unmount } = withSetup(() => usePosOperatorLock({}));
    await expect(result.unlock(1, "0000")).resolves.toBe(false);
    expect(result.error.value).toBe("PIN incorreto");
    expect(refreshMock).not.toHaveBeenCalled();
    unmount();
  });

  it("unlock que lança usa a mensagem aninhada em data.error, senão fallback", async () => {
    callMock.mockRejectedValueOnce({ data: { error: { message: "Conta travada" } } });
    const { result, unmount } = withSetup(() => usePosOperatorLock({}));
    await expect(result.unlock(1, "1234")).resolves.toBe(false);
    expect(result.error.value).toBe("Conta travada");
    unmount();
  });

  it("lock reconcilia a sessão MESMO se a chamada ao servidor falhar (local-first)", async () => {
    callMock.mockRejectedValueOnce(new Error("offline"));
    const { result, unmount } = withSetup(() => usePosOperatorLock({}));
    await result.lock();
    expect(callMock).toHaveBeenCalledOnce();
    expect(refreshMock).toHaveBeenCalledOnce();
    unmount();
  });

  it("changePin: sucesso retorna true; falha expõe o detail do servidor", async () => {
    const { result, unmount } = withSetup(() => usePosOperatorLock({}));
    callMock.mockResolvedValueOnce({});
    await expect(result.changePin(1, "1234", "5678")).resolves.toBe(true);
    expect(result.changeError.value).toBe("");
    callMock.mockRejectedValueOnce({ data: { detail: "PIN muito fraco" } });
    await expect(result.changePin(1, "1234", "5")).resolves.toBe(false);
    expect(result.changeError.value).toBe("PIN muito fraco");
    unmount();
  });
});
