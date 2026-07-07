import { describe, expect, it } from "vitest";

import {
  courierFailed,
  courierSteps,
  courierTone,
  courierToneBadge,
} from "../app/presentation/courier";

describe("courierSteps", () => {
  it("marks the search phase as current while distributing/waiting", () => {
    for (const letter of ["D", "G", "P", "U"]) {
      const steps = courierSteps(letter);
      expect(steps.map((s) => s.state)).toEqual(["current", "pending", "pending", "pending"]);
    }
  });

  it("advances to accepted when the driver takes the ride (A) or waits at the shop (S)", () => {
    for (const letter of ["A", "S"]) {
      const steps = courierSteps(letter);
      expect(steps.map((s) => s.state)).toEqual(["done", "current", "pending", "pending"]);
    }
  });

  it("shows picked-up as current when out for delivery (E)", () => {
    expect(courierSteps("E").map((s) => s.state)).toEqual(["done", "done", "current", "pending"]);
  });

  it("completes every step when finished (F)", () => {
    expect(courierSteps("F").map((s) => s.state)).toEqual(["done", "done", "done", "done"]);
  });

  it("returns no steps for failed or unknown statuses", () => {
    expect(courierSteps("N")).toEqual([]);
    expect(courierSteps("C")).toEqual([]);
    expect(courierSteps("")).toEqual([]);
    expect(courierSteps("Z")).toEqual([]);
  });

  it("labels the four phases in board order", () => {
    expect(courierSteps("D").map((s) => s.label)).toEqual([
      "Solicitado",
      "Aceito",
      "Coletado",
      "Entregue",
    ]);
  });
});

describe("courierTone", () => {
  it("maps ride phases to tones", () => {
    expect(courierTone("D")).toBe("muted");
    expect(courierTone("A")).toBe("info");
    expect(courierTone("S")).toBe("info");
    expect(courierTone("E")).toBe("active");
    expect(courierTone("F")).toBe("success");
    expect(courierTone("N")).toBe("danger");
    expect(courierTone("C")).toBe("danger");
    expect(courierTone("")).toBe("muted");
  });

  it("every tone resolves to badge classes", () => {
    for (const letter of ["D", "A", "E", "F", "N", ""]) {
      expect(courierToneBadge(courierTone(letter))).toBeTruthy();
    }
  });
});

describe("courierFailed", () => {
  it("only N and C are failures", () => {
    expect(courierFailed("N")).toBe(true);
    expect(courierFailed("C")).toBe(true);
    expect(courierFailed("F")).toBe(false);
    expect(courierFailed("E")).toBe(false);
  });
});
