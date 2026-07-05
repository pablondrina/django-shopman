import { beforeEach, describe, expect, it } from "vitest";

import { installNuxtGlobals } from "../support/composableEnv";
import { useOrdersBoard } from "../../app/composables/useOrdersBoard";
import type { TwoZoneQueueProjection } from "../../app/types/orders";

const env = installNuxtGlobals();

function emptyZone(): TwoZoneQueueProjection {
  return {
    entrada: [],
    preparing_count: 0,
    preparo: [],
    saida_retirada: [],
    saida_delivery: [],
    saida_delivery_transit: [],
    saida_delivery_count: 0,
    saida_count: 0,
    total_count: 0,
  };
}

describe("useOrdersBoard — derivação da fila", () => {
  beforeEach(() => env.reset());

  it("deriva queue/zones/totalCount da projection", () => {
    const queue = { ...emptyZone(), entrada: [{ ref: "WEB-1" }] as never[], total_count: 3 };
    env.fetchData.value = { queue };
    const board = useOrdersBoard();
    expect(board.queue.value).toEqual(queue);
    expect(board.totalCount.value).toBe(3);
    expect(board.zones.value[0]!.key).toBe("entrada");
    expect(board.zones.value[0]!.count).toBe(1);
  });

  it("degrada para null/[]/0 quando o payload vem vazio", () => {
    env.fetchData.value = null;
    const board = useOrdersBoard();
    expect(board.queue.value).toBeNull();
    expect(board.zones.value).toEqual([]);
    expect(board.totalCount.value).toBe(0);
  });

  it("expõe `realtime` começando em 'polling' (SSE liga no onMounted, browser)", () => {
    // Sem componente montado (harness node), o SSE não conecta → sinal honesto de poll.
    expect(useOrdersBoard().realtime.value).toBe("polling");
  });
});

describe("useOrdersBoard — ações (act)", () => {
  beforeEach(() => {
    env.reset();
    env.fetchData.value = { queue: emptyZone() };
  });

  it("confirm posta em /orders/{ref}/confirm/ e reconcilia via refresh", async () => {
    const board = useOrdersBoard();
    const ok = await board.confirm("WEB-1");
    expect(ok).toBe(true);
    const [path, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(path)).toBe("/api/v1/backstage/orders/WEB-1/confirm/");
    expect(opts.method).toBe("POST");
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(board.isBusy("WEB-1")).toBe(false);
  });

  it("reject envia reason + cancellation_code", async () => {
    const board = useOrdersBoard();
    await board.reject("IFOOD-9", "Sem estoque", "CODE_2");
    const [path, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(path)).toBe("/api/v1/backstage/orders/IFOOD-9/reject/");
    expect(opts.body).toEqual({ reason: "Sem estoque", cancellation_code: "CODE_2" });
  });

  it("falha na ação acende erro inline por-ref + toast, e devolve false", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Pagamento não confirmado" } });
    const board = useOrdersBoard();
    const ok = await board.confirm("WEB-2");
    expect(ok).toBe(false);
    expect(board.actionError("WEB-2")).toBe("Pagamento não confirmado");
    expect(env.sonner.error).toHaveBeenCalledWith("Pagamento não confirmado");
    expect(env.refresh).not.toHaveBeenCalled();
  });

  it("uma nova tentativa limpa o erro anterior do ref", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "boom" } });
    const board = useOrdersBoard();
    await board.confirm("WEB-3");
    expect(board.actionError("WEB-3")).toBe("boom");
    await board.advance("WEB-3");
    expect(board.actionError("WEB-3")).toBe("");
  });

  it("guarda de reentrância: 2º clique enquanto em voo não dispara 2º POST", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise<void>((res) => { release = res; }));
    const board = useOrdersBoard();
    const first = board.advance("WEB-4");
    expect(board.isBusy("WEB-4")).toBe(true);
    const second = await board.advance("WEB-4");
    expect(second).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
    expect(board.isBusy("WEB-4")).toBe(false);
  });
});

describe("useOrdersBoard — bulk + reasons", () => {
  beforeEach(() => {
    env.reset();
    env.fetchData.value = { queue: emptyZone() };
  });

  it("actMany dispara todos, reconcilia UMA vez e conta falhas", async () => {
    env.fetchMock
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce({ data: { detail: "x" } })
      .mockResolvedValueOnce({});
    const board = useOrdersBoard();
    const failures = await board.confirmMany(["WEB-1", "WEB-2", "WEB-3"]);
    expect(failures).toBe(1);
    expect(env.fetchMock).toHaveBeenCalledTimes(3);
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(board.actionError("WEB-2")).toBe("x");
  });

  it("fetchCancellationReasons devolve a lista, ou [] em erro", async () => {
    env.fetchMock.mockResolvedValueOnce({ reasons: [{ code: "1", description: "Sem estoque" }] });
    const board = useOrdersBoard();
    expect(await board.fetchCancellationReasons("IFOOD-1")).toEqual([{ code: "1", description: "Sem estoque" }]);
    env.fetchMock.mockRejectedValueOnce(new Error("net"));
    expect(await board.fetchCancellationReasons("IFOOD-2")).toEqual([]);
  });
});
