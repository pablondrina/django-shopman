import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAdaptivePoll } from "~/composables/useAdaptivePoll";

// useAdaptivePoll owns the app's refresh cadence: visibility-aware, floored, and
// re-reading interval() each tick. Driven here with fake timers + a document shim +
// captured lifecycle hooks (the harness's no-op onMounted would never schedule).
let mountedCb: (() => void) | null;
let unmountCb: (() => void) | null;
let visibilityListener: (() => void) | null;
const doc = {
  hidden: false,
  addEventListener: (event: string, cb: () => void) => {
    if (event === "visibilitychange") visibilityListener = cb;
  },
  removeEventListener: () => {},
};

beforeEach(() => {
  vi.useFakeTimers();
  mountedCb = null;
  unmountCb = null;
  visibilityListener = null;
  doc.hidden = false;
  vi.stubGlobal("onMounted", (cb: () => void) => (mountedCb = cb));
  vi.stubGlobal("onBeforeUnmount", (cb: () => void) => (unmountCb = cb));
  vi.stubGlobal("document", doc);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useAdaptivePoll", () => {
  it("refreshes once per interval after mount", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    useAdaptivePoll(refresh, () => 30_000);
    mountedCb!();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("skips the fetch while the tab is hidden (parked tablet costs zero)", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    doc.hidden = true;
    useAdaptivePoll(refresh, () => 30_000);
    mountedCb!();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("floors the interval at 5s even when the caller asks for less", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    useAdaptivePoll(refresh, () => 1_000);
    mountedCb!();
    await vi.advanceTimersByTimeAsync(4_999);
    expect(refresh).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("re-reads interval() each tick, so cadence can tighten under pressure", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    let ms = 30_000;
    useAdaptivePoll(refresh, () => ms);
    mountedCb!();
    ms = 10_000; // something went late — takes effect at the next reschedule
    await vi.advanceTimersByTimeAsync(30_000); // first (30s) timer fires → reschedules @ 10s
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(10_000); // the tightened 10s cadence fires
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("refreshes immediately when the tab becomes visible again", () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    useAdaptivePoll(refresh, () => 30_000);
    mountedCb!();
    refresh.mockClear();
    doc.hidden = false;
    visibilityListener!();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("stops polling after unmount (no leaked timer)", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    useAdaptivePoll(refresh, () => 30_000);
    mountedCb!();
    unmountCb!();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(refresh).not.toHaveBeenCalled();
  });
});
