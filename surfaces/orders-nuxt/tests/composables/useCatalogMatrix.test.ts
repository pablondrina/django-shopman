import { beforeEach, describe, expect, it } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useCatalogMatrix } from "../../app/composables/useCatalogMatrix";

const env = installNuxtGlobals();

describe("useCatalogMatrix — leitura + célula", () => {
  beforeEach(() => env.reset());

  it("deriva matrix da projection", () => {
    env.fetchData.value = { matrix: { products: [], surfaces: [] } };
    expect(useCatalogMatrix().matrix.value).toEqual({ products: [], surfaces: [] });
  });

  it("setCell posta {sku, surface_ref, ...patch} e reconcilia; key por-célula", async () => {
    const m = useCatalogMatrix();
    expect(await m.setCell("PAO", "web", { is_sellable: false })).toBe(true);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/cell/");
    expect(opts.body).toEqual({ sku: "PAO", surface_ref: "web", is_sellable: false });
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(m.cellKey("PAO", "web")).toBe("PAO@web");
  });

  it("setProduct posta {sku, ...patch} (globalzinho por produto)", async () => {
    const m = useCatalogMatrix();
    await m.setProduct("PAO", { is_published: false });
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/product/");
    expect(opts.body).toEqual({ sku: "PAO", is_published: false });
  });

  it("guarda de reentrância por-célula", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise<void>((r) => { release = r; }));
    const m = useCatalogMatrix();
    const first = m.setCell("PAO", "web", { is_sellable: true });
    expect(m.isBusy(m.cellKey("PAO", "web"))).toBe(true);
    expect(await m.setCell("PAO", "web", { is_sellable: false })).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
  });

  it("falha na célula acende errorMsg + toast + false", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Sem preço na superfície" } });
    const m = useCatalogMatrix();
    expect(await m.setCell("PAO", "web", { is_published: true })).toBe(false);
    expect(m.errorMsg.value).toBe("Sem preço na superfície");
    expect(env.sonner.error).toHaveBeenCalledWith("Sem preço na superfície");
  });
});

describe("useCatalogMatrix — lote + reordenação", () => {
  beforeEach(() => env.reset());

  it("bulkSet devolve count e tosta sucesso", async () => {
    env.fetchMock.mockResolvedValueOnce({ count: 5 });
    const m = useCatalogMatrix();
    const n = await m.bulkSet("web", { collection_ref: "c1" }, { is_published: true });
    expect(n).toBe(5);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/bulk/");
    expect(opts.body).toEqual({ surface_ref: "web", collection_ref: "c1", is_published: true });
    expect(env.sonner.success).toHaveBeenCalledWith("5 item(ns) atualizado(s).");
  });

  it("bulkPrice envia op/value e escopo por skus", async () => {
    env.fetchMock.mockResolvedValueOnce({ count: 3 });
    const m = useCatalogMatrix();
    const n = await m.bulkPrice("web", { skus: ["PAO"] }, { op: "pct", value: 10 });
    expect(n).toBe(3);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/bulk-price/");
    expect(opts.body).toEqual({ surface_ref: "web", skus: ["PAO"], op: "pct", value: 10 });
  });

  it("bulkSet em voo bloqueia 2ª chamada (bulkBusy)", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise((r) => { release = r; }));
    const m = useCatalogMatrix();
    const first = m.bulkSet("web", {}, { is_published: true });
    expect(m.bulkBusy.value).toBe(true);
    expect(await m.bulkSet("web", {}, { is_published: false })).toBe(0);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
  });

  it("reorderItems reverte (refresh) e tosta em falha", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Ordem inválida" } });
    const m = useCatalogMatrix();
    expect(await m.reorderItems("c1", ["A", "B"])).toBe(false);
    expect(env.refresh).toHaveBeenCalledTimes(1); // revert do otimista
    expect(env.sonner.error).toHaveBeenCalledWith("Ordem inválida");
  });
});

describe("useCatalogMatrix — sync + PIM (Arc H)", () => {
  beforeEach(() => env.reset());

  it("resync(sku, platform) posta {sku, platform} e reconcilia", async () => {
    const m = useCatalogMatrix();
    expect(await m.resync("PAO", "ifood")).toBe(true);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/resync/");
    expect(opts.body).toEqual({ sku: "PAO", platform: "ifood" });
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(env.sonner.success).toHaveBeenCalledWith("Reenvio agendado.");
  });

  it("resync(sku) sem plataforma reenvia a todas", async () => {
    const m = useCatalogMatrix();
    await m.resync("PAO");
    const [, opts] = env.fetchMock.mock.calls[0]!;
    expect(opts.body).toEqual({ sku: "PAO" });
    expect(env.sonner.success).toHaveBeenCalledWith("Reenvio agendado em todas as plataformas.");
  });

  it("resync em voo bloqueia a 2ª chamada (mesma célula)", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise<void>((r) => { release = r; }));
    const m = useCatalogMatrix();
    const first = m.resync("PAO", "ifood");
    expect(m.isBusy(m.cellKey("PAO", "ifood"))).toBe(true);
    expect(await m.resync("PAO", "ifood")).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
  });

  it("saveSocial posta {sku, ...patch} e tosta sucesso", async () => {
    const m = useCatalogMatrix();
    expect(await m.saveSocial("PAO", { brand: "Nelson", hashtags: ["pao"] })).toBe(true);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/social/");
    expect(opts.body).toEqual({ sku: "PAO", brand: "Nelson", hashtags: ["pao"] });
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(m.socialKey("PAO")).toBe("social@PAO");
  });

  it("saveSocial em erro de validação acende errorMsg + false", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "GTIN inválido" } });
    const m = useCatalogMatrix();
    expect(await m.saveSocial("PAO", { gtin: "123" })).toBe(false);
    expect(m.errorMsg.value).toBe("GTIN inválido");
    expect(env.sonner.error).toHaveBeenCalledWith("GTIN inválido");
  });
});
