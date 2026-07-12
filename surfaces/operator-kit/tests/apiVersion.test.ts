// Checagem do X-API-Version no BFF: parse da major e warning estruturado em
// divergência — sem nunca quebrar o request (graceful). O carimbo vem do
// APIVersionHeaderMiddleware (shopman/shop/middleware.py).
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  EXPECTED_API_MAJOR,
  parseApiVersionMajor,
  warnOnApiVersionMismatch,
} from "../server/utils/apiVersion";

describe("parseApiVersionMajor", () => {
  it("parses a bare major", () => {
    expect(parseApiVersionMajor("1")).toBe(1);
  });

  it("parses major.minor and pre-release suffixes", () => {
    expect(parseApiVersionMajor("2.3")).toBe(2);
    expect(parseApiVersionMajor("2.0-beta")).toBe(2);
    expect(parseApiVersionMajor(" 1 ")).toBe(1);
  });

  it("returns null for missing or unparsable headers", () => {
    expect(parseApiVersionMajor(null)).toBeNull();
    expect(parseApiVersionMajor(undefined)).toBeNull();
    expect(parseApiVersionMajor("")).toBeNull();
    expect(parseApiVersionMajor("abc")).toBeNull();
  });
});

describe("warnOnApiVersionMismatch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("stays silent when the major matches", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    warnOnApiVersionMismatch(String(EXPECTED_API_MAJOR), { path: "/api/v1/backstage/orders/" });
    expect(warn).not.toHaveBeenCalled();
  });

  it("stays silent when the header is absent (routes outside /api/v1/)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    warnOnApiVersionMismatch(null, { path: "/admin/login/" });
    expect(warn).not.toHaveBeenCalled();
  });

  it("logs a structured warning when the major diverges", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    warnOnApiVersionMismatch("2", { path: "/api/v1/backstage/orders/" });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith("[shopman] X-API-Version mismatch", {
      expected_major: EXPECTED_API_MAJOR,
      received: "2",
      path: "/api/v1/backstage/orders/",
    });
  });
});
