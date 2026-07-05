import { beforeEach, describe, expect, it } from "vitest";

import { installNuxtGlobals } from "../support/composableEnv";
import { useOrderDetail } from "../../app/composables/useOrderDetail";

const env = installNuxtGlobals();

describe("useOrderDetail", () => {
  beforeEach(() => env.reset());

  it("deriva order da projection; null quando vazio", () => {
    env.fetchData.value = { order: { ref: "WEB-1", status: "confirmed" } };
    expect(useOrderDetail("WEB-1").order.value).toEqual({ ref: "WEB-1", status: "confirmed" });
    env.fetchData.value = null;
    expect(useOrderDetail("WEB-1").order.value).toBeNull();
  });

  it("confirm posta em /orders/{ref}/confirm/ e reconcilia via refresh", async () => {
    const d = useOrderDetail("WEB-1");
    expect(await d.confirm()).toBe(true);
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/orders/WEB-1/confirm/");
    expect(env.refresh).toHaveBeenCalledTimes(1);
  });

  it("reject/cancel enviam reason", async () => {
    const d = useOrderDetail("WEB-2");
    await d.reject("sem estoque");
    expect(env.fetchMock.mock.calls[0]![1].body).toEqual({ reason: "sem estoque" });
    await d.cancel("cliente desistiu");
    expect(env.fetchMock.mock.calls[1]![1].body).toEqual({ reason: "cliente desistiu" });
  });

  it("guarda de reentrância: 2ª ação enquanto em voo é no-op", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise<void>((r) => { release = r; }));
    const d = useOrderDetail("WEB-3");
    const first = d.advance();
    expect(d.busy.value).toBe(true);
    expect(await d.confirm()).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
    expect(d.busy.value).toBe(false);
  });

  it("falha → toast do detalhe do servidor + false", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Pagamento pendente" } });
    const d = useOrderDetail("WEB-4");
    expect(await d.confirm()).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("Pagamento pendente");
  });

  it("saveNotes/addComment enviam o corpo e tostam sucesso", async () => {
    const d = useOrderDetail("WEB-5");
    await d.saveNotes("frágil");
    expect(env.fetchMock.mock.calls[0]![1].body).toEqual({ notes: "frágil" });
    expect(env.sonner.success).toHaveBeenCalledWith("Notas salvas.");
    await d.addComment("ligar antes");
    expect(env.fetchMock.mock.calls[1]![1].body).toEqual({ note: "ligar antes" });
    expect(env.sonner.success).toHaveBeenCalledWith("Comentário adicionado.");
  });
});
