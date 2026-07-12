import { beforeEach, describe, expect, it } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useAlerts } from "../../app/composables/useAlerts";

const env = installNuxtGlobals();

describe("useAlerts", () => {
  beforeEach(() => env.reset());

  it("deriva alerts + contadores; degrada para []/0", () => {
    env.fetchData.value = { alerts: [{ pk: 1 }], counts: { active: 2, critical: 1 } };
    const a = useAlerts();
    expect(a.alerts.value).toEqual([{ pk: 1 }]);
    expect(a.activeCount.value).toBe(2);
    expect(a.criticalCount.value).toBe(1);

    env.fetchData.value = null;
    const b = useAlerts();
    expect(b.alerts.value).toEqual([]);
    expect(b.activeCount.value).toBe(0);
    expect(b.criticalCount.value).toBe(0);
  });

  it("ack posta em /alerts/{pk}/ack/ e reconcilia via refresh", async () => {
    const a = useAlerts();
    await a.ack(7);
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/alerts/7/ack/");
    expect(env.refresh).toHaveBeenCalledTimes(1);
  });

  it("ack com falha acende toast e não derruba", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Alerta já reconhecido" } });
    const a = useAlerts();
    await a.ack(9);
    expect(env.sonner.error).toHaveBeenCalledWith("Alerta já reconhecido");
  });
});
