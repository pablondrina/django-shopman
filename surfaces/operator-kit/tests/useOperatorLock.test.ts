import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "./support/composableEnv";
import { useOperatorLock } from "../app/composables/useOperatorLock";

const env = installNuxtGlobals();
const PERM = "backstage.operate_production";

describe("useOperatorLock — session derivations", () => {
  beforeEach(() => env.reset());

  it("reads authenticated/locked/operator/mustChange from the session projection", () => {
    env.fetchData.value = {
      device_user: "admin",
      operator: { name: "Nelson" },
      require_operator: true,
      locked: true,
      pin_must_change: true,
    };
    const { authenticated, locked, operator, requireOperator, mustChange } = useOperatorLock(PERM);
    expect(authenticated.value).toBe(true);
    expect(locked.value).toBe(true);
    expect(operator.value?.name).toBe("Nelson");
    expect(requireOperator.value).toBe(true);
    expect(mustChange.value).toBe(true);
  });

  it("treats a null session (403 = unauthenticated) as not authenticated, not locked", () => {
    env.fetchData.value = null;
    const { authenticated, locked, operator } = useOperatorLock(PERM);
    expect(authenticated.value).toBe(false);
    expect(locked.value).toBe(false);
    expect(operator.value).toBeNull();
  });

  it("is not locked when the gate is off, even with nobody operating", () => {
    env.fetchData.value = { device_user: "admin", operator: null, require_operator: false, locked: true };
    expect(useOperatorLock(PERM).locked.value).toBe(false);
  });
});

describe("useOperatorLock — unlock", () => {
  beforeEach(() => env.reset());

  it("unlocks by PIN, refreshes the session AND all board data (frees 403-stuck fetches)", async () => {
    env.fetchData.value = { device_user: "admin" };
    const { unlock } = useOperatorLock(PERM);
    const ok = await unlock({ operatorId: 3, pin: "1234" });
    expect(ok).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operator/unlock/",
      expect.objectContaining({ method: "POST", body: expect.objectContaining({ operator_id: 3, pin: "1234", perm: PERM }) }),
    );
    expect(env.refresh).toHaveBeenCalled();
    expect(env.refreshNuxtData).toHaveBeenCalled();
  });

  it("prefers the badge payload when a badge is scanned", async () => {
    env.fetchData.value = { device_user: "admin" };
    const { unlock } = useOperatorLock(PERM);
    await unlock({ badge: "abc123", pin: "9999" });
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operator/unlock/",
      expect.objectContaining({ body: { badge: "abc123", perm: PERM } }),
    );
  });

  it("toasts and returns false on a bad identification", async () => {
    env.fetchData.value = { device_user: "admin" };
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "PIN inválido" } });
    const { unlock } = useOperatorLock(PERM);
    expect(await unlock({ operatorId: 3, pin: "0000" })).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("PIN inválido");
  });

  it("ignores a concurrent unlock while one is in flight", async () => {
    env.fetchData.value = { device_user: "admin" };
    let release!: () => void;
    env.fetchMock.mockImplementationOnce(() => new Promise<void>((r) => (release = r)));
    const { unlock, busy } = useOperatorLock(PERM);
    const first = unlock({ operatorId: 3, pin: "1234" });
    expect(busy.value).toBe(true);
    expect(await unlock({ operatorId: 3, pin: "1234" })).toBe(false);
    release();
    await first;
    expect(busy.value).toBe(false);
  });
});

describe("useOperatorLock — lock / changePin / eligible", () => {
  beforeEach(() => env.reset());

  it("lock is best-effort (POST then refresh)", async () => {
    env.fetchData.value = { device_user: "admin" };
    await useOperatorLock(PERM).lock();
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operator/lock/",
      expect.objectContaining({ method: "POST" }),
    );
    expect(env.refresh).toHaveBeenCalled();
  });

  it("changePin succeeds and clears the error", async () => {
    env.fetchData.value = { device_user: "admin" };
    const { changePin, changeError } = useOperatorLock(PERM);
    expect(await changePin({ currentPin: "1234", newPin: "5678" })).toBe(true);
    expect(changeError.value).toBe("");
  });

  it("changePin exposes the server message on failure", async () => {
    env.fetchData.value = { device_user: "admin" };
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "PIN atual errado" } });
    const { changePin, changeError } = useOperatorLock(PERM);
    expect(await changePin({ currentPin: "0000", newPin: "5678" })).toBe(false);
    expect(changeError.value).toBe("PIN atual errado");
  });

  it("loadEligible falls back to an empty list on error (never throws to the UI)", async () => {
    env.fetchData.value = { device_user: "admin" };
    env.fetchMock.mockRejectedValueOnce(new Error("down"));
    const { loadEligible, eligible } = useOperatorLock(PERM);
    await loadEligible();
    expect(eligible.value).toEqual([]);
  });
});
