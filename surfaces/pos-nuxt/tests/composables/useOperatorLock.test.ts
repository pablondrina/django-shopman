import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApp } from "vue";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";

import type { OperatorCard } from "~/utils/operatorLock";

// Estado do lock de operador do POS. Mockamos o transporte (usePosAction) e exercemos
// os ramos de sucesso/erro do unlock/lock/changePin — o caminho de risco não-testado.
const { callMock } = vi.hoisted(() => ({ callMock: vi.fn() }));
mockNuxtImport("usePosAction", () => () => ({ call: callMock }));

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

describe("useOperatorLock", () => {
  beforeEach(() => callMock.mockReset());

  it("unlock com sucesso fixa o operador ativo e destrava", async () => {
    callMock.mockResolvedValue({ ok: true, operator: ana });
    const { result, unmount } = withSetup(() => useOperatorLock({ initialOperator: null }));
    expect(result.locked.value).toBe(true);
    await expect(result.unlock(1, "1234")).resolves.toBe(true);
    expect(result.activeOperator.value).toEqual(ana);
    expect(result.locked.value).toBe(false);
    expect(result.error.value).toBe("");
    unmount();
  });

  it("unlock com ok:false expõe a mensagem do servidor e mantém travado", async () => {
    callMock.mockResolvedValue({ ok: false, error: { message: "PIN incorreto" } });
    const { result, unmount } = withSetup(() => useOperatorLock({}));
    await expect(result.unlock(1, "0000")).resolves.toBe(false);
    expect(result.error.value).toBe("PIN incorreto");
    expect(result.locked.value).toBe(true);
    unmount();
  });

  it("unlock que lança usa a mensagem aninhada em data.error, senão fallback", async () => {
    callMock.mockRejectedValueOnce({ data: { error: { message: "Conta travada" } } });
    const { result, unmount } = withSetup(() => useOperatorLock({}));
    await expect(result.unlock(1, "1234")).resolves.toBe(false);
    expect(result.error.value).toBe("Conta travada");
    unmount();
  });

  it("lock limpa o operador MESMO se a chamada ao servidor falhar (local-first)", async () => {
    const { result, unmount } = withSetup(() => useOperatorLock({ initialOperator: ana }));
    expect(result.locked.value).toBe(false);
    callMock.mockRejectedValueOnce(new Error("offline"));
    await result.lock();
    expect(result.activeOperator.value).toBeNull();
    expect(result.locked.value).toBe(true);
    unmount();
  });

  it("changePin: sucesso retorna true; falha expõe o detail do servidor", async () => {
    const { result, unmount } = withSetup(() => useOperatorLock({}));
    callMock.mockResolvedValueOnce({});
    await expect(result.changePin(1, "1234", "5678")).resolves.toBe(true);
    expect(result.changeError.value).toBe("");
    callMock.mockRejectedValueOnce({ data: { detail: "PIN muito fraco" } });
    await expect(result.changePin(1, "1234", "5")).resolves.toBe(false);
    expect(result.changeError.value).toBe("PIN muito fraco");
    unmount();
  });
});
