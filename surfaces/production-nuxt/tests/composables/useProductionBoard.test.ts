import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { defaultPlanningDate, useProductionBoard } from "~/composables/useProductionBoard";

const env = installNuxtGlobals();

function boardPayload(overrides: Record<string, unknown> = {}) {
  return {
    board: {
      selected_date: "2026-07-06",
      selected_date_display: "domingo, 6 de julho",
      selected_position_ref: "",
      access: {},
      base_recipes: [],
      matrix_rows: [{ output_sku: "PAO-001", recipe_name: "Pão", planned_qty: "0" }],
      counts: { planned: 3, started: 1, finished: 0 },
      ...overrides,
    },
  };
}

describe("useProductionBoard — read derivations", () => {
  beforeEach(() => env.reset());

  it("derives board/rows/counts/dateDisplay from the fetch payload", () => {
    env.fetchData.value = boardPayload();
    const { board, rows, counts, dateDisplay } = useProductionBoard();
    expect(board.value?.selected_date).toBe("2026-07-06");
    expect(rows.value).toHaveLength(1);
    expect(counts.value?.planned).toBe(3);
    expect(dateDisplay.value).toBe("domingo, 6 de julho");
  });

  it("degrades to safe empties when the payload is null (never throws)", () => {
    env.fetchData.value = null;
    const { board, rows, counts, dateDisplay } = useProductionBoard();
    expect(board.value).toBeNull();
    expect(rows.value).toEqual([]);
    expect(counts.value).toBeNull();
    expect(dateDisplay.value).toBe("");
  });
});

describe("useProductionBoard — plan/start writes", () => {
  beforeEach(() => env.reset());

  it("plan POSTs to the plan endpoint and reconciles via refresh on success", async () => {
    env.fetchData.value = boardPayload();
    const { plan } = useProductionBoard();
    const res = await plan("PAO-001", { recipe_id: 5, quantity: "12", target_date: "2026-07-06" });
    expect(res.ok).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/plan/",
      expect.objectContaining({ method: "POST", body: expect.objectContaining({ recipe_id: 5, quantity: "12" }) }),
    );
    expect(env.refresh).toHaveBeenCalledOnce();
  });

  it("start POSTs to the per-WO start endpoint", async () => {
    env.fetchData.value = boardPayload();
    const { start } = useProductionBoard();
    const res = await start("PAO-001", 42, "30");
    expect(res.ok).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/42/start/",
      expect.objectContaining({ method: "POST", body: { quantity: "30" } }),
    );
  });

  it("guards against a second in-flight write on the same row (optimistic dedup)", async () => {
    env.fetchData.value = boardPayload();
    let release!: () => void;
    env.fetchMock.mockImplementationOnce(() => new Promise<void>((r) => (release = r)));
    const { plan, isBusy } = useProductionBoard();

    const first = plan("PAO-001", { recipe_id: 5, quantity: "12", target_date: "2026-07-06" });
    expect(isBusy("PAO-001")).toBe(true);
    const second = await plan("PAO-001", { recipe_id: 5, quantity: "9", target_date: "2026-07-06" });
    expect(second.ok).toBe(false); // rejected while first still in flight
    expect(env.fetchMock).toHaveBeenCalledTimes(1);

    release();
    await first;
    expect(isBusy("PAO-001")).toBe(false); // rolled back after settle
  });

  it("surfaces a structured shortage instead of a toast when the server reports one", async () => {
    env.fetchData.value = boardPayload();
    env.fetchMock.mockRejectedValueOnce({ data: { error: { code: "material_shortage", missing: [] } } });
    const { plan } = useProductionBoard();
    const res = await plan("PAO-001", { recipe_id: 5, quantity: "12", target_date: "2026-07-06" });
    expect(res.ok).toBe(false);
    expect(res.shortage?.code).toBe("material_shortage");
    expect(env.sonner.error).not.toHaveBeenCalled();
  });

  it("toasts a friendly message on a generic failure", async () => {
    env.fetchData.value = boardPayload();
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Banco fora do ar" } });
    const { start } = useProductionBoard();
    const res = await start("PAO-001", 42, "30");
    expect(res.ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("Banco fora do ar");
  });
});

describe("defaultPlanningDate", () => {
  it("plans today in the morning, tomorrow after noon (baker's calm-afternoon rhythm)", () => {
    expect(defaultPlanningDate(new Date(2026, 6, 6, 9, 0))).toBe("2026-07-06");
    expect(defaultPlanningDate(new Date(2026, 6, 6, 13, 0))).toBe("2026-07-07");
  });
});
