import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useBlindMap } from "~/composables/useBlindMap";

const env = installNuxtGlobals();

describe("useBlindMap", () => {
  beforeEach(() => env.reset());

  it("derives the code ↔ prep rows for the manager view", () => {
    env.fetchData.value = {
      blind_map: {
        selected_date: "2026-07-17",
        selected_date_display: "17/07/2026",
        rows: [
          { code: "B7", name: "Massa ciabatta", output_quantity_display: "25 un." },
          { code: "M3", name: "Massa brioche", output_quantity_display: "12 un." },
        ],
      },
    };
    const { blindMap, rows } = useBlindMap(ref("2026-07-17"));

    expect(blindMap.value?.selected_date_display).toBe("17/07/2026");
    expect(rows.value.map((row) => row.code)).toEqual(["B7", "M3"]);
  });

  it("degrades to empty rows when the payload is null", () => {
    env.fetchData.value = null;
    const { blindMap, rows } = useBlindMap(ref("2026-07-17"));
    expect(blindMap.value).toBeNull();
    expect(rows.value).toEqual([]);
  });
});
