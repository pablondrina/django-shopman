import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useProductionManagement } from "~/composables/useProductionManagement";

const env = installNuxtGlobals();

describe("useProductionManagement", () => {
  beforeEach(() => env.reset());

  it("derives the day KPIs and the late-order list", () => {
    env.fetchData.value = {
      management: {
        selected_date: "2026-07-17",
        average_yield_rate: "90%",
        capacity_percent: 50,
        late_orders: [{ pk: 1, ref: "WO-009", elapsed_minutes: 45, target_minutes: 30 }],
      },
    };
    const { management, lateOrders, forbidden } = useProductionManagement(ref("2026-07-17"));

    expect(management.value?.average_yield_rate).toBe("90%");
    expect(management.value?.capacity_percent).toBe(50);
    expect(lateOrders.value).toHaveLength(1);
    expect(lateOrders.value[0]?.ref).toBe("WO-009");
    expect(forbidden.value).toBe(false);
  });

  it("degrades to empty when the payload is null", () => {
    env.fetchData.value = null;
    const { management, lateOrders } = useProductionManagement(ref("2026-07-17"));
    expect(management.value).toBeNull();
    expect(lateOrders.value).toEqual([]);
  });
});
