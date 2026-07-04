import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";

// Read-window do terminal: derivação das fatias (pos/shift/tabs/operators/actions) a
// partir da Projection serializada. Mockamos useFetch para controlar o payload.
const { fetchResult } = vi.hoisted(() => ({ fetchResult: { value: null as unknown } }));

mockNuxtImport("useFetch", () => () => fetchResult.value);
mockNuxtImport("useRequestHeaders", () => () => ({}));
mockNuxtImport("useRuntimeConfig", () => () => ({ app: { baseURL: "/" } }));

function asyncData(payload: unknown) {
  return { data: ref(payload), pending: ref(false), error: ref(null), refresh: vi.fn() };
}

describe("usePosTerminal", () => {
  beforeEach(() => {
    fetchResult.value = null;
  });

  it("deriva as fatias da Projection", async () => {
    const pos = { actions: [{ ref: "fire" }], operators: [{ id: 1, name: "Ana" }] };
    fetchResult.value = asyncData({ pos, shift: { open: true }, tabs: [{ ref: "T1" }] });
    const t = await usePosTerminal();
    expect(t.pos.value).toEqual(pos);
    expect(t.shift.value).toEqual({ open: true });
    expect(t.tabs.value).toEqual([{ ref: "T1" }]);
    expect(t.operators.value).toEqual([{ id: 1, name: "Ana" }]);
    expect(t.actions.value).toEqual([{ ref: "fire" }]);
  });

  it("degrada para null/[] quando o payload vem vazio", async () => {
    fetchResult.value = asyncData(null);
    const t = await usePosTerminal();
    expect(t.pos.value).toBeNull();
    expect(t.shift.value).toBeNull();
    expect(t.tabs.value).toEqual([]);
    expect(t.operators.value).toEqual([]);
    expect(t.actions.value).toEqual([]);
  });
});
