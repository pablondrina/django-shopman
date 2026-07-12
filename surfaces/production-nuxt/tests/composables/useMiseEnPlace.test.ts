import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useMiseEnPlace } from "~/composables/useMiseEnPlace";

const env = installNuxtGlobals();

describe("useMiseEnPlace", () => {
  beforeEach(() => env.reset());

  it("derives the projection + lines for the day", () => {
    env.fetchData.value = { mise_en_place: { selected_date: "2026-07-06", lines: [{ sku: "FARINHA" }, { sku: "SAL" }] } };
    const { projection, lines } = useMiseEnPlace(ref("2026-07-06"));
    expect(projection.value?.selected_date).toBe("2026-07-06");
    expect(lines.value).toHaveLength(2);
  });

  it("toggles the shift-local 'separado' check and counts it (in-memory, no server write)", () => {
    env.fetchData.value = { mise_en_place: { selected_date: "2026-07-06", lines: [{ sku: "FARINHA" }, { sku: "SAL" }] } };
    const { toggleChecked, isChecked, checkedCount } = useMiseEnPlace(ref("2026-07-06"));

    expect(isChecked("FARINHA")).toBe(false);
    toggleChecked("FARINHA");
    expect(isChecked("FARINHA")).toBe(true);
    expect(checkedCount.value).toBe(1);

    toggleChecked("FARINHA"); // untick
    expect(isChecked("FARINHA")).toBe(false);
    expect(checkedCount.value).toBe(0);
  });

  it("degrades to empty when the payload is null", () => {
    env.fetchData.value = null;
    const { projection, lines } = useMiseEnPlace(ref("2026-07-06"));
    expect(projection.value).toBeNull();
    expect(lines.value).toEqual([]);
  });
});
