import { describe, expect, it } from "vitest";

import {
  appendPinDigit,
  backspacePin,
  isIdleBeyond,
} from "../app/utils/operatorLock";

describe("operator lock — idle / auto-lock", () => {
  it("locks once idle reaches the timeout", () => {
    expect(isIdleBeyond(0, 60_000, 60)).toBe(true);
    expect(isIdleBeyond(0, 59_000, 60)).toBe(false);
  });

  it("never auto-locks when timeout is disabled (<= 0)", () => {
    expect(isIdleBeyond(0, 9_999_999, 0)).toBe(false);
    expect(isIdleBeyond(0, 9_999_999, -1)).toBe(false);
  });
});

describe("operator lock — PIN buffer", () => {
  it("appends only digits up to maxLength", () => {
    expect(appendPinDigit("12", "3", 4)).toBe("123");
    expect(appendPinDigit("123", "4", 4)).toBe("1234");
    expect(appendPinDigit("1234", "5", 4)).toBe("1234"); // capped
    expect(appendPinDigit("12", "a", 4)).toBe("12"); // non-digit ignored
  });

  it("backspaces the last digit", () => {
    expect(backspacePin("123")).toBe("12");
    expect(backspacePin("")).toBe("");
  });
});
