import { describe, expect, it } from "vitest";
import "../../../operator-kit/tests/support/installGlobals"; // stubs `ref` etc. before the singleton module evaluates
import { useFlapClack } from "~/composables/useFlapClack";

// useFlapClack is a device-local singleton; its Web Audio noise/clack is client-only
// (e2e/manual). The unit-observable part is the on/off preference toggle.
describe("useFlapClack", () => {
  it("defaults to enabled and toggles the sound preference", () => {
    const sound = useFlapClack();
    expect(sound.enabled.value).toBe(true);
    sound.toggle();
    expect(sound.enabled.value).toBe(false);
    sound.toggle();
    expect(sound.enabled.value).toBe(true);
  });

  it("clack/unlock are no-ops without audio unlocked (never throw)", () => {
    const sound = useFlapClack();
    expect(() => sound.clack()).not.toThrow();
    expect(() => sound.unlock()).not.toThrow();
  });
});
