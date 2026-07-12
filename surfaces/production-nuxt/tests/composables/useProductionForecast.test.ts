import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useProductionForecast } from "~/composables/useProductionForecast";

const env = installNuxtGlobals();

describe("useProductionForecast", () => {
  beforeEach(() => env.reset());

  it("derives forecast + rows from the payload", () => {
    env.fetchData.value = { forecast: { selected_date: "2026-07-06", rows: [{ sku: "A" }, { sku: "B" }] } };
    const { forecast, rows } = useProductionForecast();
    expect(forecast.value?.selected_date).toBe("2026-07-06");
    expect(rows.value).toHaveLength(2);
  });

  it("degrades to null/empty when the payload is null", () => {
    env.fetchData.value = null;
    const { forecast, rows } = useProductionForecast();
    expect(forecast.value).toBeNull();
    expect(rows.value).toEqual([]);
  });

  it("defaults the selected date to today's ISO", () => {
    env.fetchData.value = null;
    const { selectedDate } = useProductionForecast();
    expect(selectedDate.value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
