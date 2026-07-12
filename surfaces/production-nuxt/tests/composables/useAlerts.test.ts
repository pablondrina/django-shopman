import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useAlerts } from "~/composables/useAlerts";

const env = installNuxtGlobals();

describe("useAlerts", () => {
  beforeEach(() => env.reset());

  it("derives alerts and the active/critical counts", () => {
    env.fetchData.value = { alerts: [{ pk: 1 }, { pk: 2 }], counts: { active: 2, critical: 1 } };
    const { alerts, activeCount, criticalCount } = useAlerts();
    expect(alerts.value).toHaveLength(2);
    expect(activeCount.value).toBe(2);
    expect(criticalCount.value).toBe(1);
  });

  it("degrades to zero when the payload is null", () => {
    env.fetchData.value = null;
    const { alerts, activeCount, criticalCount } = useAlerts();
    expect(alerts.value).toEqual([]);
    expect(activeCount.value).toBe(0);
    expect(criticalCount.value).toBe(0);
  });

  it("ack POSTs to the per-alert endpoint and reconciles", async () => {
    env.fetchData.value = { alerts: [], counts: {} };
    await useAlerts().ack(9);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/alerts/9/ack/",
      expect.objectContaining({ method: "POST" }),
    );
    expect(env.refresh).toHaveBeenCalled();
  });

  it("toasts if ack fails", async () => {
    env.fetchData.value = { alerts: [], counts: {} };
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "sem rede" } });
    await useAlerts().ack(9);
    expect(env.sonner.error).toHaveBeenCalledWith("sem rede");
  });
});
