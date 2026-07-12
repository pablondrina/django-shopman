import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useWeighing } from "~/composables/useWeighing";

const env = installNuxtGlobals();

describe("useWeighing", () => {
  beforeEach(() => env.reset());

  it("derives tickets + date display", () => {
    env.fetchData.value = {
      weighing: { selected_date_display: "domingo", tickets: [{ code: "D06" }, { code: "D07" }] },
    };
    const { tickets, dateDisplay } = useWeighing(ref("2026-07-06"));
    expect(tickets.value).toHaveLength(2);
    expect(dateDisplay.value).toBe("domingo");
  });

  it("degrades to empty when the payload is null", () => {
    env.fetchData.value = null;
    const { tickets, dateDisplay } = useWeighing(ref("2026-07-06"));
    expect(tickets.value).toEqual([]);
    expect(dateDisplay.value).toBe("");
  });
});
