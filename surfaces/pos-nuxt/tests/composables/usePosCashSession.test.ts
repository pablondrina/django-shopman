import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";
import { computed, ref } from "vue";

import type { Action, POSProjection } from "~/types/pos";
import { usePosCashSession } from "~/composables/usePosCashSession";

import { makeProjection } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function makeCashSession(opts: {
  projection?: POSProjection | null;
  actionCall?: ReturnType<typeof vi.fn>;
} = {}) {
  const posValue = ref<POSProjection | null>(
    opts.projection === undefined ? makeProjection() : opts.projection,
  );
  const actionsValue = ref<Action[]>([]);
  const actionCall = opts.actionCall ?? vi.fn().mockResolvedValue({});
  const refresh = vi.fn().mockResolvedValue(undefined);
  const session = usePosCashSession({
    pos: computed(() => posValue.value),
    actions: computed(() => actionsValue.value),
    refresh,
    action: { call: actionCall },
  });
  return { session, posValue, actionCall, refresh };
}

describe("usePosCashSession — sessão de caixa (antesala)", () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
  });

  it("movementKinds cai no default quando a capability não veio", () => {
    const { session } = makeCashSession();
    expect(session.movementKinds.value).toEqual(["sangria", "suprimento", "ajuste"]);
  });

  it("movementKinds lê a capability do contrato quando presente", () => {
    const projection = makeProjection({
      checkout: {
        intent_version: 1,
        capabilities: { cash_management: { movement_kinds: ["sangria"] } },
      } as POSProjection["checkout"],
    });
    const { session } = makeCashSession({ projection });
    expect(session.movementKinds.value).toEqual(["sangria"]);
  });

  it("shiftRequiredForSale segue o contrato (default seguro = exigido)", () => {
    const { session } = makeCashSession();
    expect(session.shiftRequiredForSale.value).toBe(true);
    const optOut = makeProjection({
      checkout: {
        intent_version: 1,
        capabilities: { cash_management: { requires_open_shift_for_sale: false } },
      } as POSProjection["checkout"],
    });
    const { session: relaxed } = makeCashSession({ projection: optOut });
    expect(relaxed.shiftRequiredForSale.value).toBe(false);
  });

  it("abrir caixa envia valor + terminal, dá refresh e devolve true", async () => {
    const { session, actionCall, refresh } = makeCashSession();
    const ok = await session.openCashShift("50,00");
    expect(ok).toBe(true);
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/open/",
      { body: { opening_amount: "50,00", terminal_ref: "T1" } },
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("falha vira toast e devolve false (sem engolir silenciosamente)", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("boom"));
    const { session, refresh } = makeCashSession({ actionCall });
    const ok = await session.closeCashShift({ amount: "10", notes: "" });
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
    expect(session.busy.value).toBe(false);
  });

  it("guarda de reentrância: busy bloqueia novo comando", async () => {
    const { session, actionCall } = makeCashSession();
    session.busy.value = true;
    const ok = await session.registerCashMovement({ kind: "sangria", amount: "5", reason: "troco" });
    expect(ok).toBe(false);
    expect(actionCall).not.toHaveBeenCalled();
  });

  it("fechar turno bloqueante envia shift_id e contagem cega", async () => {
    const { session, actionCall } = makeCashSession();
    await session.closeBlockingShift({ shift_id: 7, amount: "", notes: "turno órfão" });
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/close-blocking/",
      { body: { shift_id: 7, closing_amount: "0", notes: "turno órfão" } },
    );
  });

  it("movimento envia kind/valor/motivo", async () => {
    const { session, actionCall } = makeCashSession();
    await session.registerCashMovement({ kind: "suprimento", amount: "20,00", reason: "troco" });
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/movement/",
      { body: { kind: "suprimento", amount: "20,00", reason: "troco" } },
    );
  });
});
