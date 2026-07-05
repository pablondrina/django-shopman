import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";

// Read-window da Central: deriva tiles/operatorName da projection. Mockamos useFetch.
const { fetchResult } = vi.hoisted(() => ({ fetchResult: { value: null as unknown } }));

mockNuxtImport("useFetch", () => () => fetchResult.value);
mockNuxtImport("useRequestHeaders", () => () => ({}));
mockNuxtImport("useRuntimeConfig", () => () => ({ app: { baseURL: "/" } }));

function asyncData(payload: unknown) {
  return { data: ref(payload), pending: ref(false), error: ref(null), refresh: vi.fn() };
}

describe("useOperatorHub", () => {
  beforeEach(() => {
    fetchResult.value = null;
  });

  it("deriva tiles e nome do operador da projection", async () => {
    const hub = { operator_name: "Ana", tiles: [{ ref: "pos", label: "PDV", icon: "banknote", url: "/x", kind: "launch", description: "" }] };
    fetchResult.value = asyncData({ hub });
    const h = await useOperatorHub();
    expect(h.operatorName.value).toBe("Ana");
    expect(h.tiles.value).toHaveLength(1);
    expect(h.tiles.value[0]!.ref).toBe("pos");
    expect(h.hub.value).toEqual(hub);
  });

  it("degrada para []/'' quando o payload vem vazio", async () => {
    fetchResult.value = asyncData(null);
    const h = await useOperatorHub();
    expect(h.hub.value).toBeNull();
    expect(h.tiles.value).toEqual([]);
    expect(h.operatorName.value).toBe("");
  });
});
