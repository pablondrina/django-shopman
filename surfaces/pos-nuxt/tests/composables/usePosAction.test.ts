import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";

// Transporte de mutação do POS: $fetch com credenciais + header CSRF do cookie.
const { cookieRef, fetchMock } = vi.hoisted(() => ({
  cookieRef: { value: "" },
  fetchMock: vi.fn(),
}));

mockNuxtImport("useCookie", () => () => cookieRef);
mockNuxtImport("useRuntimeConfig", () => () => ({ app: { baseURL: "/" } }));

vi.stubGlobal("$fetch", fetchMock);

describe("usePosAction", () => {
  beforeEach(() => {
    fetchMock.mockReset().mockResolvedValue({ ok: true });
    cookieRef.value = "";
  });

  it("posta com credenciais e sem X-CSRFToken quando não há cookie", async () => {
    const { call } = usePosAction();
    await call("/api/v1/backstage/operator/lock/");
    const [path, opts] = fetchMock.mock.calls[0];
    expect(String(path)).toContain("/api/v1/backstage/operator/lock/");
    expect(opts.method).toBe("POST");
    expect(opts.credentials).toBe("include");
    expect(opts.headers).toEqual({});
  });

  it("injeta X-CSRFToken do cookie e repassa method/body", async () => {
    cookieRef.value = "tok123";
    const { call } = usePosAction();
    await call("/api/v1/backstage/pos/tabs/save/", { method: "PUT", body: { tab_ref: "T1" } });
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.headers).toEqual({ "X-CSRFToken": "tok123" });
    expect(opts.method).toBe("PUT");
    expect(opts.body).toEqual({ tab_ref: "T1" });
  });

  it("propaga o valor de retorno do $fetch (tipado)", async () => {
    fetchMock.mockResolvedValue({ ok: true, tab: { ref: "T9" } });
    const { call } = usePosAction();
    await expect(call("/x/")).resolves.toEqual({ ok: true, tab: { ref: "T9" } });
  });

  it("re-gate: 401 (auth perdida) marca a sessão expirada e re-lança", async () => {
    useOperatorSession().reset();
    fetchMock.mockRejectedValue({ status: 401, data: { detail: "expired" } });
    const { call } = usePosAction();
    await expect(call("/api/v1/backstage/pos/sale/close/")).rejects.toBeTruthy();
    expect(useOperatorSession().expired.value).toBe(true);
  });

  it("403 (proibido) NÃO dispara re-gate — só re-lança", async () => {
    useOperatorSession().reset();
    fetchMock.mockRejectedValue({ status: 403 });
    const { call } = usePosAction();
    await expect(call("/x/")).rejects.toBeTruthy();
    expect(useOperatorSession().expired.value).toBe(false);
  });
});
