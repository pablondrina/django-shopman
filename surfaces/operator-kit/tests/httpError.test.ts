import { describe, expect, it } from "vitest";
import { httpError, isTransientError } from "../app/utils/httpError";

describe("httpError", () => {
  it("extracts status/data/message from an ofetch-style error", () => {
    const info = httpError({ status: 409, data: { error: "conflict" }, message: "boom" });
    expect(info).toEqual({ status: 409, data: { error: "conflict" }, message: "boom" });
  });

  it("falls back to statusCode and nested response", () => {
    expect(httpError({ statusCode: 500 }).status).toBe(500);
    expect(httpError({ response: { status: 503, _data: { x: 1 } } })).toMatchObject({
      status: 503,
      data: { x: 1 },
    });
  });

  it("returns status 0 for a non-http value", () => {
    expect(httpError(new Error("network down"))).toMatchObject({ status: 0, message: "network down" });
    expect(httpError(undefined).status).toBe(0);
  });
});

describe("isTransientError", () => {
  it("treats network (0) and 502/503/504 as transient", () => {
    expect(isTransientError(new Error("offline"))).toBe(true);
    for (const status of [502, 503, 504]) expect(isTransientError({ status })).toBe(true);
  });

  it("does NOT retry 4xx (except 429, handled elsewhere) or 500", () => {
    for (const status of [400, 401, 403, 404, 409, 429, 500]) {
      expect(isTransientError({ status })).toBe(false);
    }
  });
});
