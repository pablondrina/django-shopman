import { describe, expect, it } from "vitest";
import "../../../operator-kit/tests/support/installGlobals"; // stubs `ref` etc. before the singleton module evaluates
import { useOvenTimers } from "~/composables/useOvenTimers";

// useOvenTimers is a device-local singleton (its ticker + chime + AudioContext are
// client-only, so ringing/sound is e2e/manual territory). Here we cover the pure,
// unit-observable part: the arm→get→clear dictionary and the minutes clamp.
describe("useOvenTimers", () => {
  it("arms a timer under its key and reads it back; clear removes it", () => {
    const oven = useOvenTimers();
    oven.arm("wo-1", 15);
    expect(oven.get("wo-1")?.minutes).toBe(15);
    oven.clear("wo-1");
    expect(oven.get("wo-1")).toBeNull();
  });

  it("clamps minutes to a whole number ≥ 1 (no zero/sub-minute reminders)", () => {
    const oven = useOvenTimers();
    oven.arm("wo-clamp-a", 0.4);
    expect(oven.get("wo-clamp-a")?.minutes).toBe(1);
    oven.arm("wo-clamp-b", 15.7);
    expect(oven.get("wo-clamp-b")?.minutes).toBe(16);
    oven.clear("wo-clamp-a");
    oven.clear("wo-clamp-b");
  });

  it("a freshly armed timer is not yet ringing", () => {
    const oven = useOvenTimers();
    oven.arm("wo-2", 20);
    expect(oven.isRinging("wo-2")).toBe(false);
    oven.clear("wo-2");
  });

  it("get/isRinging/remainingLabel are safe for an unknown key", () => {
    const oven = useOvenTimers();
    expect(oven.get("nope")).toBeNull();
    expect(oven.isRinging("nope")).toBe(false);
    expect(oven.remainingLabel("nope")).toBe("");
  });
});
