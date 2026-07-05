import { describe, expect, it } from "vitest";
import { httpError, httpErrorMessage, isTransientError, isUnauthenticatedError } from "../app/utils/httpError";

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

describe("httpErrorMessage", () => {
  it("prioriza data.detail (DRF)", () => {
    expect(httpErrorMessage({ data: { detail: "Comanda já paga" } }, "fallback")).toBe("Comanda já paga");
  });

  it("cai para data.error.message (erro de domínio)", () => {
    expect(httpErrorMessage({ data: { error: { message: "Estoque insuficiente" } } }, "fallback")).toBe(
      "Estoque insuficiente",
    );
  });

  it("usa o fallback localizado — nunca a string técnica do ofetch", () => {
    expect(httpErrorMessage({ message: "[POST] \"/x\": 500" }, "Falha ao salvar.")).toBe("Falha ao salvar.");
    expect(httpErrorMessage(new Error("Failed to fetch"), "Sem conexão.")).toBe("Sem conexão.");
    expect(httpErrorMessage({ data: { detail: "" } }, "Falha.")).toBe("Falha."); // detail vazio → fallback
  });
});

describe("isUnauthenticatedError", () => {
  it("is true only for 401 (auth perdida), across error shapes", () => {
    expect(isUnauthenticatedError({ status: 401 })).toBe(true);
    expect(isUnauthenticatedError({ statusCode: 401 })).toBe(true);
    expect(isUnauthenticatedError({ response: { status: 401 } })).toBe(true);
  });

  it("is false for 403 (proibido) e demais status/rede", () => {
    for (const status of [0, 400, 403, 404, 419, 500]) {
      expect(isUnauthenticatedError({ status })).toBe(false);
    }
    expect(isUnauthenticatedError(new Error("offline"))).toBe(false);
  });
});
