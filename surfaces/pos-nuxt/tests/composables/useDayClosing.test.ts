import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { toast } from "vue-sonner";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";

// Fechamento do DIA na antesala: leitura da projection + comando de contagem
// cega. Mockamos useFetch para controlar o payload; o POST vai pelo action.call.
const { fetchResult } = vi.hoisted(() => ({ fetchResult: { value: null as unknown } }));

mockNuxtImport("useFetch", () => () => fetchResult.value);
mockNuxtImport("useRequestHeaders", () => () => ({}));

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function asyncData(payload: unknown, error: unknown = null) {
  return { data: ref(payload), pending: ref(false), error: ref(error), refresh: vi.fn() };
}

const CLOSING = {
  today: "2026-07-17",
  today_display: "17/07/2026",
  items: [{ sku: "PAO", name: "Pão", qty_available: 3, classification: "d1" }],
  has_items: true,
  already_closed: false,
  existing_closing_display: "",
  has_old_d1: false,
  total_available: 3,
  production_summary: {},
  reconciliation_errors: [],
  pending_production: [],
  has_pending_production: false,
  upcoming_preorders: [],
  has_upcoming_preorders: false,
};

describe("useDayClosing", () => {
  beforeEach(() => {
    fetchResult.value = asyncData({ closing: CLOSING });
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
  });

  it("deriva a projection e não acusa accessDenied em 200", async () => {
    const d = await useDayClosing({ action: { call: vi.fn() } });
    expect(d.closing.value?.today).toBe("2026-07-17");
    expect(d.accessDenied.value).toBe(false);
  });

  it("401/403 viram accessDenied (gate é da API)", async () => {
    fetchResult.value = asyncData(null, { statusCode: 403 });
    const d = await useDayClosing({ action: { call: vi.fn() } });
    expect(d.closing.value).toBeNull();
    expect(d.accessDenied.value).toBe(true);
  });

  it("submit envia quantities pelo action.call, dá refresh e devolve true", async () => {
    const data = asyncData({ closing: CLOSING });
    fetchResult.value = data;
    const call = vi.fn().mockResolvedValue({ ok: true });
    const d = await useDayClosing({ action: { call } });
    const ok = await d.submit({ PAO: "2" });
    expect(ok).toBe(true);
    expect(call).toHaveBeenCalledWith(
      "/api/v1/backstage/closing/",
      { body: { quantities: { PAO: "2" } } },
    );
    expect(data.refresh).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalled();
  });

  it("falha (ex.: 409 dia já fechado) vira toast + refresh + false", async () => {
    const data = asyncData({ closing: CLOSING });
    fetchResult.value = data;
    const call = vi.fn().mockRejectedValue(new Error("já fechado"));
    const d = await useDayClosing({ action: { call } });
    const ok = await d.submit({ PAO: "2" });
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalled();
    expect(data.refresh).toHaveBeenCalled();
    expect(d.submitting.value).toBe(false);
  });

  it("guarda de reentrância: submitting bloqueia novo envio", async () => {
    const call = vi.fn();
    const d = await useDayClosing({ action: { call } });
    d.submitting.value = true;
    const ok = await d.submit({ PAO: "2" });
    expect(ok).toBe(false);
    expect(call).not.toHaveBeenCalled();
  });
});
