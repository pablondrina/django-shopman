import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useProductionReports } from "~/composables/useProductionReports";
import type { ReportFiltersQuery } from "~/presentation/reports";

const env = installNuxtGlobals();

function filters(overrides: Partial<ReportFiltersQuery> = {}): ReportFiltersQuery {
  return {
    report_kind: "history",
    date_from: "2026-07-10",
    date_to: "2026-07-17",
    recipe_ref: "",
    position_ref: "",
    operator_ref: "",
    ...overrides,
  };
}

describe("useProductionReports", () => {
  beforeEach(() => env.reset());

  it("derives the three row sets and the filter options", () => {
    env.fetchData.value = {
      reports: {
        filters: { report_kind: "history", date_from: "2026-07-10", date_to: "2026-07-17" },
        history_rows: [{ ref: "WO-001" }, { ref: "WO-002" }],
        operator_rows: [{ operator_ref: "ana" }],
        waste_rows: [{ recipe_ref: "pao" }],
        available_recipes: [{ ref: "pao", name: "Pão" }],
        available_positions: [{ ref: "forno", name: "Forno" }],
      },
    };
    const { historyRows, operatorRows, wasteRows, availableRecipes, availablePositions, forbidden } =
      useProductionReports(ref(filters()));

    expect(historyRows.value).toHaveLength(2);
    expect(operatorRows.value).toHaveLength(1);
    expect(wasteRows.value).toHaveLength(1);
    expect(availableRecipes.value[0]?.name).toBe("Pão");
    expect(availablePositions.value[0]?.ref).toBe("forno");
    expect(forbidden.value).toBe(false);
  });

  it("builds the CSV link from the active filters (direct download, format=csv)", () => {
    env.fetchData.value = null;
    const { csvUrl } = useProductionReports(
      ref(filters({ report_kind: "recipe_waste", recipe_ref: "pao" })),
    );
    const params = new URLSearchParams(csvUrl.value.split("?")[1]);
    expect(params.get("format")).toBe("csv");
    expect(params.get("report_kind")).toBe("recipe_waste");
    expect(params.get("recipe_ref")).toBe("pao");
  });

  it("degrades to empty rows when the payload is null", () => {
    env.fetchData.value = null;
    const { reports, historyRows, operatorRows, wasteRows } = useProductionReports(ref(filters()));
    expect(reports.value).toBeNull();
    expect(historyRows.value).toEqual([]);
    expect(operatorRows.value).toEqual([]);
    expect(wasteRows.value).toEqual([]);
  });
});
