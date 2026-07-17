import { describe, expect, it } from "vitest";
import {
  REPORT_KINDS,
  capacityLabel,
  reportKindLabel,
  reportsCsvUrl,
  reportsQuery,
  type ReportFiltersQuery,
} from "~/presentation/reports";

const FILTERS: ReportFiltersQuery = {
  report_kind: "history",
  date_from: "2026-07-10",
  date_to: "2026-07-17",
  recipe_ref: "",
  position_ref: "forno",
  operator_ref: "",
};

describe("reportKindLabel", () => {
  it("labels the three report kinds in pt-br", () => {
    expect(reportKindLabel("history")).toBe("Histórico");
    expect(reportKindLabel("operator_productivity")).toBe("Produtividade");
    expect(reportKindLabel("recipe_waste")).toBe("Desperdício");
  });

  it("exposes the kinds in the tab order of the page", () => {
    expect(REPORT_KINDS.map((entry) => entry.kind)).toEqual([
      "history",
      "operator_productivity",
      "recipe_waste",
    ]);
  });
});

describe("reportsQuery", () => {
  it("keeps only non-empty filters", () => {
    expect(reportsQuery(FILTERS)).toEqual({
      report_kind: "history",
      date_from: "2026-07-10",
      date_to: "2026-07-17",
      position_ref: "forno",
    });
  });
});

describe("reportsCsvUrl", () => {
  it("links the same endpoint with format=csv and the active filters", () => {
    const url = reportsCsvUrl(FILTERS);
    expect(url.startsWith("/api/v1/backstage/production/reports/?")).toBe(true);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("format")).toBe("csv");
    expect(params.get("report_kind")).toBe("history");
    expect(params.get("date_from")).toBe("2026-07-10");
    expect(params.get("position_ref")).toBe("forno");
    expect(params.get("recipe_ref")).toBeNull();
  });
});

describe("capacityLabel", () => {
  it("renders percent when configured and empty when not", () => {
    expect(capacityLabel(50)).toBe("50%");
    expect(capacityLabel(0)).toBe("0%");
    expect(capacityLabel(null)).toBe("");
  });
});
