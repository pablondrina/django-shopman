import { describe, expect, it } from "vitest";

import {
  appendPinDigit,
  buildUnlockPayload,
  canSubmitPin,
  isLikelyBadge,
  isLocked,
  operatorName,
} from "../app/presentation/operatorLock";
import type { OperatorSession } from "../app/types/operator";

const session = (over: Partial<OperatorSession> = {}): OperatorSession => ({
  require_operator: true,
  device_user: "estacao",
  operator: null,
  locked: true,
  ...over,
});

describe("isLocked", () => {
  it("locks only when the gate is on AND nobody is operating", () => {
    expect(isLocked(session())).toBe(true);
    expect(
      isLocked(
        session({
          operator: { id: 1, username: "bia", name: "Bia" },
          locked: false,
        }),
      ),
    ).toBe(false);
    // gate off → never locked, regardless of locked flag
    expect(isLocked(session({ require_operator: false }))).toBe(false);
    expect(isLocked(null)).toBe(false);
  });
});

describe("operatorName", () => {
  it("prefers the display name, falls back to username", () => {
    expect(
      operatorName(
        session({ operator: { id: 1, username: "bia", name: "Bia Forno" } }),
      ),
    ).toBe("Bia Forno");
    expect(
      operatorName(session({ operator: { id: 1, username: "bia", name: "" } })),
    ).toBe("bia");
    expect(operatorName(session())).toBe("");
  });
});

describe("isLikelyBadge", () => {
  it("recognises a 24-hex badge token, rejects PINs and junk", () => {
    expect(isLikelyBadge("a1b2c3d4e5f6a1b2c3d4e5f6")).toBe(true);
    expect(isLikelyBadge("  A1B2C3D4E5F6A1B2C3D4E5F6  ")).toBe(true);
    expect(isLikelyBadge("1234")).toBe(false);
    expect(isLikelyBadge("not-hex-zzzz")).toBe(false);
    expect(isLikelyBadge("a1b2c3")).toBe(false); // too short
  });
});

describe("buildUnlockPayload", () => {
  it("uses the badge when present (with perm)", () => {
    expect(
      buildUnlockPayload({
        badge: " tok ",
        perm: "backstage.operate_production",
      }),
    ).toEqual({
      badge: "tok",
      perm: "backstage.operate_production",
    });
  });
  it("uses operator_id + pin otherwise", () => {
    expect(
      buildUnlockPayload({ operatorId: 7, pin: " 4321 ", perm: "p" }),
    ).toEqual({
      operator_id: 7,
      pin: "4321",
      perm: "p",
    });
  });
  it("omits perm when absent", () => {
    expect(buildUnlockPayload({ operatorId: 7, pin: "4321" })).toEqual({
      operator_id: 7,
      pin: "4321",
    });
  });
});

describe("canSubmitPin", () => {
  it("requires a picked operator and a 4+ digit pin", () => {
    expect(canSubmitPin(null, "4321")).toBe(false);
    expect(canSubmitPin(7, "12")).toBe(false);
    expect(canSubmitPin(7, "4321")).toBe(true);
  });
});

describe("appendPinDigit", () => {
  it("appends digits, ignores non-digits, caps length", () => {
    expect(appendPinDigit("12", "3")).toBe("123");
    expect(appendPinDigit("12", "a")).toBe("12");
    expect(appendPinDigit("12345678", "9")).toBe("12345678"); // capped at 8
  });
});
